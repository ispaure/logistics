"""Local candidates and interrupted-copy evidence never imply device support."""
from dataclasses import asdict
from hashlib import sha256
from io import BytesIO
import json
import unittest
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from commonUtils.runtime.operations import OperationCancelled
from commonUtils.testing.stages import TestStage
from features.notebooks.editor import Editor
from features.notebooks.notebook import Notebook, json_bytes, read_archive
from features.notebooks.remarkable_transfer import compare_upload_members, prepare_upload
from Python.tests.notebooks.image_fixtures import locked_book, paste_action

TEST_STAGE = TestStage.REGRESSION


def archive_bytes(members):
    output = BytesIO()
    with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return output.getvalue()


def fixture(*, template='Blank'):
    book = Notebook.new('Synthetic upload', template=template)
    editor = Editor(book)
    editor.apply(dict(op='stroke', points=[[100, 100, .5], [200, 200, 1]], tool=17, width=2))
    editor.apply(paste_action())
    return book


class RemarkableTransferTests(unittest.TestCase):
    def test_native_candidate_is_byte_exact_with_images_and_opaque_members(self):
        book = fixture()
        book.members[book.id + '/opaque/future.bin'] = b'untouched opaque data'
        source = book.to_bytes()
        candidate = prepare_upload(source)
        self.assertIs(candidate.archive, source)
        self.assertEqual(candidate.receipt.source_sha256, sha256(source).hexdigest())
        self.assertEqual(candidate.receipt.archive_sha256, candidate.receipt.source_sha256)
        self.assertEqual(candidate.receipt.document_id, book.id)
        self.assertEqual(candidate.receipt.page_ids, tuple(page.id for page in book.pages))
        self.assertFalse(candidate.receipt.converted_backgrounds)
        self.assertTrue(compare_upload_members(candidate.receipt, read_archive(source)).complete)
        self.assertNotIn('Synthetic upload', json.dumps(asdict(candidate.receipt)))

    def test_modern_records_and_deleted_pages_are_preserved_without_rewriting(self):
        book = fixture()
        members = read_archive(book.to_bytes())
        content = json.loads(members[book.id + '.content'])
        content.pop('pages')
        content['formatVersion'] = 2
        deleted = str(uuid4())
        content['cPages'] = dict(pages=[dict(id=book.pages[0].id, idx=dict(timestamp='1:1', value='ba'),
            future=dict(preserve=True)), dict(id=deleted, deleted=dict(timestamp='1:2', value=1))], future='preserve')
        members[book.id + '.content'] = json_bytes(content)
        members[f'{book.id}/{deleted}.rm'] = b'opaque deleted-page scene'
        source = archive_bytes(members)
        candidate = prepare_upload(source)
        self.assertEqual(candidate.archive, source)
        self.assertEqual(candidate.receipt.page_ids, (book.pages[0].id,))
        self.assertEqual(read_archive(candidate.archive), members)

    def test_modern_page_table_with_legacy_or_unqualified_version_is_rejected(self):
        book = fixture(template='Logistics Grid')
        members = read_archive(book.to_bytes())
        content = json.loads(members[book.id + '.content'])
        content.pop('pages')
        content['cPages'] = dict(pages=[dict(id=book.pages[0].id, idx=dict(timestamp='1:1', value='ba'))])
        for version in (None, 1, 3, '2', True):
            with self.subTest(version=version):
                content['formatVersion'] = version
                members[book.id + '.content'] = json_bytes(content)
                source = archive_bytes(members)
                with self.assertRaisesRegex(ValueError, 'Modern page tables require formatVersion 2'):
                    prepare_upload(source)
                # Conservative preparation does not change opaque read/retrieval.
                self.assertEqual(Notebook.read(source).members, members)

    def test_custom_background_preparation_preserves_ink_images_and_source(self):
        book = fixture(template='Logistics Grid')
        source = book.to_bytes()
        original = read_archive(source)
        candidate = prepare_upload(source)
        result = Notebook.read(candidate.archive)
        self.assertTrue(candidate.receipt.converted_backgrounds)
        self.assertEqual(candidate.receipt.file_type, 'pdf')
        self.assertNotEqual(candidate.receipt.source_sha256, candidate.receipt.archive_sha256)
        self.assertEqual(candidate.receipt.document_id, book.id)
        self.assertEqual(read_archive(source), original)
        for name, value in original.items():
            if not name.endswith(('.metadata', '.content', '.pagedata')):
                self.assertEqual(result.members[name], value)
        self.assertEqual(result.pages[0].record['redir']['value'], 0)
        self.assertEqual(prepare_upload(candidate.archive).archive, candidate.archive)

    def test_existing_pdf_is_exact_but_missing_background_and_encryption_are_rejected(self):
        candidate = prepare_upload(fixture(template='Logistics Dots').to_bytes())
        self.assertEqual(prepare_upload(candidate.archive).archive, candidate.archive)
        members = read_archive(candidate.archive)
        content = json.loads(members[candidate.receipt.document_id + '.content'])
        content['redirectionPageMap'] = [100]
        members[candidate.receipt.document_id + '.content'] = json_bytes(content)
        with self.assertRaisesRegex(ValueError, 'missing embedded PDF'):
            prepare_upload(archive_bytes(members))
        with self.assertRaisesRegex(ValueError, 'Encrypted PDF'):
            prepare_upload(locked_book().to_bytes())

    def test_incomplete_or_unsupported_active_pages_fail_without_rewriting(self):
        book = fixture()
        source = read_archive(book.to_bytes())
        image = next(name for name in source if name.endswith('.png'))
        scene = f'{book.id}/{book.pages[0].id}.rm'
        for name, value, message in ((image, None, 'Missing notebook image'),
                                     (image, b'bad PNG', 'Invalid PNG'),
                                     (scene, b'unsupported scene', 'Unsupported native page')):
            with self.subTest(name=name, value=value):
                members = dict(source)
                if value is None:
                    del members[name]
                else:
                    members[name] = value
                data = archive_bytes(members)
                before = sha256(data).digest()
                with self.assertRaisesRegex(ValueError, message):
                    prepare_upload(data)
                self.assertEqual(sha256(data).digest(), before)

    def test_unavailable_templates_and_epub_remain_outside_preparation(self):
        book = fixture()
        book.pages[0].template = 'Unverified custom artwork'
        book.structure_dirty = True
        with self.assertRaisesRegex(ValueError, 'template is unavailable'):
            prepare_upload(book.to_bytes())
        members = read_archive(fixture().to_bytes())
        content_name = next(name for name in members if name.endswith('.content'))
        content = json.loads(members[content_name])
        content['fileType'] = 'epub'
        members[content_name] = json_bytes(content)
        with self.assertRaisesRegex(ValueError, 'EPUB-backed'):
            prepare_upload(archive_bytes(members))

    def test_unrelated_members_and_trash_metadata_are_not_upload_candidates(self):
        book = fixture()
        members = read_archive(book.to_bytes())
        with self.assertRaisesRegex(ValueError, 'outside the selected document'):
            prepare_upload(archive_bytes(dict(members, unrelated=b'not part of the notebook')))
        metadata = json.loads(members[book.id + '.metadata'])
        metadata['parent'] = 'trash'
        members[book.id + '.metadata'] = json_bytes(metadata)
        with self.assertRaisesRegex(ValueError, 'live document'):
            prepare_upload(archive_bytes(members))

    def test_recovery_comparison_detects_partial_conflicting_and_foreign_members(self):
        candidate = prepare_upload(fixture().to_bytes())
        observed = read_archive(candidate.archive)
        missing = next(iter(observed))
        changed = next(name for name in observed if name != missing)
        del observed[missing]
        observed[changed] = bytes(len(observed[changed]))  # Same length, different bytes.
        observed['foreign-file'] = b'not owned by this operation'
        before = dict(observed)
        comparison = compare_upload_members(candidate.receipt, observed)
        self.assertFalse(comparison.complete)
        self.assertEqual(comparison.missing, (missing,))
        self.assertEqual(comparison.changed, (changed,))
        self.assertEqual(comparison.unexpected, ('foreign-file',))
        self.assertEqual(observed, before)
        empty = compare_upload_members(candidate.receipt, {})
        self.assertEqual(set(empty.missing), {member.name for member in candidate.receipt.members})

    def test_cancellation_stops_validation_and_comparison(self):
        source = fixture().to_bytes()
        checks = 0

        def cancelled():
            nonlocal checks
            checks += 1
            return checks == 4

        with self.assertRaises(OperationCancelled):
            prepare_upload(source, cancelled=cancelled)
        candidate = prepare_upload(source)
        with self.assertRaises(OperationCancelled):
            compare_upload_members(candidate.receipt, read_archive(source), cancelled=lambda: True)
