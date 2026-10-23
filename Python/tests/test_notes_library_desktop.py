"""Real desktop Notes Library documents: lazy providers, navigation and revocation."""
from pathlib import Path
from unittest.mock import patch
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.runtime.resources.local import LocalFiles
from features.text_editor.ui.notes_library import NotesLibraryWindow
from features.text_editor.notes_actions import actions
from models.folder_entry import FolderEntry
from models.local_folder import LocalFolder


class RemoteFiles(LocalFiles):
    private = remote_storage = True
    def __init__(self, root):
        super().__init__(root);self.calls=[];self.closed=False
    def list(self, path='', **kw):
        self.calls.append(path);return super().list(path, **kw)
    def _check_active(self):
        if self.closed:raise ValueError('Credentials revoked')
    def acquire(self):return self.close
    def close(self):self.closed=True


class NotesLibraryDesktopTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def test_note_reads_complete_short_chunks_and_enforce_the_total_preview_limit(self):
        from contextlib import contextmanager
        from io import BytesIO
        from features.text_editor.notes import NotesLibrary, MAX_NOTE
        class ShortReads(BytesIO):
            def read(self, count):
                return super().read(min(3, count))
        with self.temporary_directory() as directory:
            root = Path(directory)
            data = b'# Complete note\n'
            (root / 'Note.md').write_bytes(data)
            provider = LocalFiles(root)
            library = NotesLibrary(provider)
            @contextmanager
            def opened(path):
                with ShortReads(data) as stream:
                    yield stream
            for limit in (4, MAX_NOTE):
                with self.subTest(limit=limit), patch.object(provider, 'open', side_effect=opened), \
                        patch('features.text_editor.notes.MAX_NOTE', limit):
                    if limit < len(data):
                        with self.assertRaisesRegex(ValueError, 'too large'):
                            library.read('Note.md')
                    else:
                        self.assertEqual(library.read('Note.md'), data)

    def fixture(self, root):
        (root/'.obsidian').mkdir();(root/'Nested').mkdir()
        (root/'Home.md').write_text('# Home\n\n[Next](Nested/Next.md)')
        (root/'Nested/Next.md').write_text('# Next\n\nA nested note.')
        (root/'.obsidian/private.md').write_text('# Hidden')
        (root/'Other.txt').write_text('Not Markdown')

    def test_location_action_and_documents_host_open_library(self):
        from commonUtils.ui.document_host import register_document_host
        from desktop.documents import DocumentsPage
        with self.temporary_directory() as directory:
            root=Path(directory);self.fixture(root)
            commands=actions(FolderEntry('Notes',local=LocalFolder(root)))
            self.assertEqual([item.name for item in commands], ['Open Notes Library'])
            host=DocumentsPage(lambda: None);host.show();register_document_host(host)
            try:
                window=commands[0].callback()
                self.wait_until(lambda:not window.progress.busy)
                self.assertIn(window,host.records)
                self.assertIsNotNone(window.search)
                self.assertEqual(window.tree.topLevelItemCount(),2)
                window.open_note('Home.md');self.wait_until(lambda:not window.progress.busy)
                self.assertIn('Home',window.viewer.browser.toPlainText())
                window.open_note('Nested/Next.md');self.wait_until(lambda:not window.progress.busy)
                self.assertIn('nested note',window.viewer.browser.toPlainText())
                window.navigate(-1);self.wait_until(lambda:not window.progress.busy)
                self.assertEqual(window.history[window.index],'Home.md')
                window.search.setText('Home')
                self.assertFalse(window.items['Home.md'].isHidden())
            finally:
                self.app._commonutils_document_host = lambda: None
                host.close()

    def test_remote_no_search_no_recursive_index_and_revoked_text_clears(self):
        with self.temporary_directory() as directory:
            root=Path(directory);self.fixture(root)
            provider=RemoteFiles(root)
            window=NotesLibraryWindow(lambda:provider,'Remote',remote=True)
            window.show();self.wait_until(lambda:not window.progress.busy)
            self.assertIsNone(window.search)
            self.assertFalse(window.viewer.find_action.isVisible())
            self.assertFalse(window.viewer.find_action.isEnabled())
            self.assertEqual(provider.calls,[''])
            self.assertNotIn('Nested/Next.md',window.items)
            window.items['Nested'].setExpanded(True)
            self.wait_until(lambda:not window.progress.busy)
            self.assertEqual(provider.calls,['','Nested'])
            window.open_note('Nested/Next.md');self.wait_until(lambda:not window.progress.busy)
            self.assertIn('nested note',window.viewer.browser.toPlainText())
            window.retire()
            self.assertEqual(window.storage.data,b'')
            self.assertIsNone(window.viewer.document_state.source_bytes)
            self.assertTrue(provider.closed)

    def test_marker_file_and_escape_never_open(self):
        with self.temporary_directory() as directory:
            root=Path(directory);(root/'.obsidian').write_text('not directory')
            self.assertEqual(actions(FolderEntry('Not a vault',local=LocalFolder(root))),[])
            (root/'.obsidian').unlink();self.fixture(root)
            window=NotesLibraryWindow(lambda:LocalFiles(root),'Notes')
            window.show();self.wait_until(lambda:not window.progress.busy)
            window.open_note('../outside.md')
            self.assertFalse(window.progress.busy)
            self.assertEqual(window.storage.data,b'')
            window.open_note('.obsidian/private.md')
            self.assertEqual(window.storage.data,b'')

    def test_closing_during_listing_waits_for_worker_and_releases_provider(self):
        from threading import Event
        from shiboken6 import isValid
        with self.temporary_directory() as directory:
            root = Path(directory);self.fixture(root)
            provider = RemoteFiles(root)
            entered, released = Event(), Event()
            original = provider.list
            def blocked(path='', **kwargs):
                entered.set()
                if not released.wait(5):raise RuntimeError('Fixture timed out')
                return original(path, **kwargs)
            with patch.object(provider, 'list', side_effect=blocked):
                window = NotesLibraryWindow(lambda: provider, 'Slow remote', remote=True)
                window.show()
                try:
                    self.wait_until(entered.is_set)
                    window.close()
                    self.assertTrue(window.closing)
                    self.assertTrue(window.progress.busy)
                finally:
                    released.set()
                self.wait_until(lambda: not isValid(window) or not window.progress.busy)
                self.assertTrue(provider.closed)

    def test_late_private_read_does_not_publish_after_provider_revocation(self):
        from contextlib import contextmanager
        with self.temporary_directory() as directory:
            root = Path(directory);self.fixture(root)
            provider = RemoteFiles(root)
            window = NotesLibraryWindow(lambda: provider, 'Remote', remote=True)
            window.show();self.wait_until(lambda:not window.progress.busy)
            original = provider.open
            @contextmanager
            def revoked_read(path):
                with original(path) as stream:
                    yield stream
                provider.closed = True
            with patch.object(provider, 'open', side_effect=revoked_read):
                window.open_note('Home.md')
                from shiboken6 import isValid
                self.wait_until(lambda:not isValid(window) or not window.progress.busy)
                if isValid(window):
                    self.assertEqual(window.storage.data, b'')
                    self.assertIsNone(window.viewer.document_state.source_bytes)
