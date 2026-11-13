"""Local copy publication must honor the same boundaries as document saves."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from commonUtils.filesystem.local_access import protect_local_root
from commonUtils.runtime.resources.local import LocalFiles
from services.documents.storage import DocumentResource, export_local_document, stage_local_document_export
from unittest.mock import patch
from commonUtils.runtime.operations import OperationCancelled


class DocumentExportTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'copy.rmdoc'

    def test_export_verifies_large_binary_and_keeps_source_binding(self):
        source = self.root / 'source.rmdoc'
        source.write_bytes(b'original')
        with DocumentResource(LocalFiles(self.root), source, max_bytes=32 * 1024 * 1024) as resource:
            resource.read()
            baseline = resource.revision
            data = b'new notebook' + bytes(17 * 1024 * 1024)
            validated = []
            export_local_document(self.path, data, max_bytes=32 * 1024 * 1024,
                                  validate=lambda content: validated.append(len(content)))
            self.assertEqual(validated, [len(data), len(data)])
            self.assertEqual(self.path.read_bytes(), data)
            self.assertEqual(resource.path, source.name)
            self.assertEqual(resource.revision, baseline)
            self.assertEqual(resource.read(), b'original')

    def test_export_replaces_approved_existing_copy_but_refuses_concurrent_change(self):
        self.path.write_bytes(b'old')
        export_local_document(self.path, b'new', max_bytes=100)
        self.assertEqual(self.path.read_bytes(), b'new')
        def changed(data):
            self.path.write_bytes(b'external change')
        with self.assertRaises(ValueError):
            export_local_document(self.path, b'mine', max_bytes=100, validate=changed)
        self.assertEqual(self.path.read_bytes(), b'external change')

    def test_invalid_oversized_and_cancelled_exports_preserve_destination(self):
        self.path.write_bytes(b'original')
        for options in (dict(max_bytes=1), dict(max_bytes=100, cancelled=lambda: True),
                        dict(max_bytes=100, validate=lambda content: (_ for _ in ()).throw(ValueError('Invalid format')))):
            with self.assertRaises(Exception):
                export_local_document(self.path, b'new', **options)
            self.assertEqual(self.path.read_bytes(), b'original')

    def test_raw_export_cannot_enter_protected_root_or_replace_link(self):
        self.addCleanup(protect_local_root(object(), self.root, 'Use its provider'))
        with self.assertRaises(PermissionError):
            export_local_document(self.path, b'plaintext', max_bytes=100)
        self.assertFalse(self.path.exists())

    def test_link_target_is_preserved(self):
        target = self.root / 'target'
        target.write_bytes(b'original')
        self.path.symlink_to(target)
        with self.assertRaises(ValueError):
            export_local_document(self.path, b'new', max_bytes=100)
        self.assertTrue(self.path.is_symlink())
        self.assertEqual(target.read_bytes(), b'original')

    def test_reader_privacy_uses_wrapped_policy(self):
        from features.books.ui.reader import BooksPage
        for source, private in ((None, False), (SimpleNamespace(private=False), False),
                                (SimpleNamespace(provider=SimpleNamespace(private=True)), True),
                                (SimpleNamespace(remote_storage=True), True)):
            reader = SimpleNamespace(book=SimpleNamespace(source=source))
            self.assertEqual(BooksPage.private.fget(reader), private)

    def test_comic_ordinary_provider_is_not_private(self):
        from io import BytesIO
        from zipfile import ZipFile
        from features.comics.library import ComicDocument
        from services.documents.readers import MemorySource
        output = BytesIO()
        with ZipFile(output, 'w') as archive:
            archive.writestr('01.png', b'image')
        source = MemorySource('comic.cbz', output.getvalue())
        source.private = False
        self.assertFalse(ComicDocument('comic.cbz', source=source).private)
        source.provider = SimpleNamespace(private=True)
        self.assertTrue(ComicDocument('comic.cbz', source=source).private)


class StreamingDocumentExportTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'copy.rmdoc'
        self.path.write_bytes(b'original')
        self.provider = LocalFiles(self.root)
        self.revision = self.provider.entry(self.path.name)['revision']

    def assert_clean(self):
        self.assertEqual(list(self.root.glob('.document-export-*')), [])

    def test_default_refuses_replacement_and_approved_revision_replaces(self):
        with self.assertRaises(FileExistsError):
            with stage_local_document_export(self.path):
                self.fail('Default export admitted an existing destination')
        self.assertEqual(self.path.read_bytes(), b'original')
        with stage_local_document_export(self.path, expected_revision=self.revision) as stream:
            stream.write(b'verified new content')
            self.assertEqual(self.path.read_bytes(), b'original')
        self.assertEqual(self.path.read_bytes(), b'verified new content')
        self.assert_clean()

    def test_changed_before_staging_is_rejected(self):
        self.path.write_bytes(b'external revision')
        with self.assertRaisesRegex(ValueError, 'File changed'):
            with stage_local_document_export(self.path, expected_revision=self.revision):
                self.fail('Stale approval was accepted')
        self.assertEqual(self.path.read_bytes(), b'external revision')
        self.assert_clean()

    def test_changed_or_removed_during_export_is_preserved(self):
        for change in ('write', 'remove'):
            with self.subTest(change=change):
                self.path.write_bytes(b'original')
                revision = self.provider.entry(self.path.name)['revision']
                with self.assertRaises((ValueError, FileNotFoundError)):
                    with stage_local_document_export(self.path, expected_revision=revision) as stream:
                        stream.write(b'new')
                        if change == 'write':
                            self.path.write_bytes(b'external revision')
                        else:
                            self.path.unlink()
                if change == 'write':
                    self.assertEqual(self.path.read_bytes(), b'external revision')
                else:
                    self.assertFalse(self.path.exists())
                self.assert_clean()

    def test_new_file_appearing_during_export_is_preserved(self):
        self.path.unlink()
        with self.assertRaises(FileExistsError):
            with stage_local_document_export(self.path) as stream:
                stream.write(b'new')
                self.path.write_bytes(b'concurrent creator')
        self.assertEqual(self.path.read_bytes(), b'concurrent creator')
        self.assert_clean()

    def test_cancel_and_validation_failure_preserve_approved_file(self):
        cancelled = False
        with self.assertRaises(OperationCancelled):
            with stage_local_document_export(self.path, expected_revision=self.revision,
                                             cancelled=lambda: cancelled) as stream:
                stream.write(b'new')
                cancelled = True
        with self.assertRaisesRegex(ValueError, 'Invalid archive'):
            with stage_local_document_export(self.path, expected_revision=self.revision) as stream:
                stream.write(b'bad')
                raise ValueError('Invalid archive')
        self.assertEqual(self.path.read_bytes(), b'original')
        self.assert_clean()

    def test_failed_atomic_replace_preserves_approved_file(self):
        with patch('commonUtils.runtime.resources.local.os.replace', side_effect=PermissionError('Denied')):
            with self.assertRaises(PermissionError):
                with stage_local_document_export(self.path, expected_revision=self.revision) as stream:
                    stream.write(b'new')
        self.assertEqual(self.path.read_bytes(), b'original')
        self.assert_clean()

    def test_protected_or_linked_destination_is_rejected(self):
        release = protect_local_root(object(), self.root, 'Use its provider')
        try:
            with self.assertRaises(PermissionError):
                with stage_local_document_export(self.path, expected_revision=self.revision):
                    self.fail('Protected destination accepted')
        finally:
            release()
        other = self.root / 'original'
        self.path.rename(other)
        self.path.symlink_to(other)
        with self.assertRaises(ValueError):
            with stage_local_document_export(self.path, expected_revision=self.revision):
                self.fail('Linked destination accepted')
        self.assertEqual(other.read_bytes(), b'original')
        self.assertTrue(self.path.is_symlink())
        self.assert_clean()
