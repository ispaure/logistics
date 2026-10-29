"""Local copy publication must honor the same boundaries as document saves."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from commonUtils.filesystem.local_access import protect_local_root
from commonUtils.runtime.resources.local import LocalFiles
from services.documents.storage import DocumentResource, export_local_document


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
