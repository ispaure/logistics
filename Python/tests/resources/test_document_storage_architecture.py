"""Runtime coverage for gaps exposed by the document architecture contract."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from commonUtils.filesystem.local_access import protect_local_root
from features.notebooks.notebook import Notebook, MAX_ARCHIVE
from services.documents.storage import local_document_resource, read_local_bytes


class StorageArchitectureBehaviorTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_ordinary_binary_reads_are_bounded_and_revision_tracked(self):
        path = self.root / 'notebook.rmdoc'
        path.write_bytes(Notebook.new('Ordinary notebook').to_bytes())
        with local_document_resource(path, max_bytes=MAX_ARCHIVE) as resource:
            self.assertEqual(Notebook.read(resource.read()).name, 'Ordinary notebook')
            self.assertIsNotNone(resource.revision)
        self.assertTrue(resource.closed)
        with self.assertRaisesRegex(ValueError, 'too large'):
            read_local_bytes(path, max_bytes=1)
        with self.assertRaises(Exception):
            read_local_bytes(path, max_bytes=MAX_ARCHIVE, cancelled=lambda: True)

    def test_binary_import_refuses_protected_roots_and_links(self):
        path = self.root / 'source.rmdoc'
        path.write_bytes(Notebook.new('Protected').to_bytes())
        link = self.root / 'linked.rmdoc'
        link.symlink_to(path)
        with self.assertRaises(ValueError):
            read_local_bytes(link, max_bytes=MAX_ARCHIVE)
        self.addCleanup(protect_local_root(object(), self.root, 'Use the document provider'))
        with self.assertRaises(PermissionError):
            read_local_bytes(path, max_bytes=MAX_ARCHIVE)

    def test_pdf_and_notebook_ui_imports_cannot_open_protected_paths(self):
        from features.pdf.ui.reader import open_pdf
        from features.notebooks.ui.workspace import NotebookWorkspace
        path = self.root / 'source.rmdoc'
        path.write_bytes(Notebook.new('Protected').to_bytes())
        self.addCleanup(protect_local_root(object(), self.root, 'Use the document provider'))
        with patch('features.pdf.ui.reader.PDFWindow') as window:
            with self.assertRaises(PermissionError):
                open_pdf(path)
            window.assert_not_called()
        panel = SimpleNamespace(repository=Mock(), open=Mock(), library=Mock(), status=Mock())
        NotebookWorkspace.import_path(panel, path)
        panel.status.setText.assert_called_once_with('Use the document provider')
        panel.repository.create.assert_not_called()
        panel.open.assert_not_called()

    def test_wrapped_readonly_readers_do_not_open_metadata_editors(self):
        from features.books.ui.reader import BooksPage
        from features.comics.ui.reader import ComicReaderWindow
        for source in (SimpleNamespace(provider=SimpleNamespace(remote_storage=True)),
                       SimpleNamespace(read_only=True)):
            book = SimpleNamespace(source=source)
            with self.subTest(source=source), patch('features.books.ui.reader.MetadataEditor') as editor:
                BooksPage.edit_metadata(SimpleNamespace(book=book, worker=None))
                editor.assert_not_called()
            with patch('features.comics.ui.metadata_editor.MetadataEditor') as editor:
                ComicReaderWindow.edit_metadata(SimpleNamespace(pages=SimpleNamespace(document=book)))
                editor.assert_not_called()

    def test_notes_library_uses_wrapped_capabilities(self):
        from commonUtils.runtime.resources.local import LocalFiles
        from features.text_editor.notes import NotesLibrary
        provider = LocalFiles(self.root)
        provider.provider = SimpleNamespace(remote_storage=True)
        library = NotesLibrary(provider)
        self.assertFalse(library.writable)
        with self.assertRaisesRegex(ValueError, 'read-only'):
            library.create('Forbidden')
        self.assertFalse((self.root / 'Forbidden.md').exists())
