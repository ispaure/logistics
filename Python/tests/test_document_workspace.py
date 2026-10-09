"""Embedded documents retain state, detach safely and protect dirty buffers on close."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from commonUtils.ui import pyside as qt
from ui_new.documents import DocumentsPage, document_is_open, register_document_host, show_document
from shiboken6 import isValid


class DocumentWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.host = qt.QMainWindow()
        self.page = DocumentsPage(lambda: None, self.host)
        self.host.setCentralWidget(self.page)
        self.host.resize(1200, 800); self.host.show()
        register_document_host(self.page)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for window in tuple(self.page.records):
            if not isValid(window):
                continue
            if hasattr(window, 'documents'):
                for document in window.documents:
                    document.editor.document().setModified(False)
            window.close()
        self.host.close(); self.host.deleteLater()
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def settle(self):
        for _ in range(5): self.app.processEvents()

    def test_documents_open_embedded_and_detach_reattach_without_losing_state(self):
        window = qt.QMainWindow(); window.setWindowTitle('Document')
        edit = qt.QLineEdit('retained'); window.setCentralWidget(edit)
        show_document(window); self.settle()
        self.assertFalse(window.isWindow())
        self.assertEqual(self.page.tabs.count(), 1)
        self.page.detach_current(); self.settle()
        self.assertTrue(window.isWindow())
        self.assertEqual(self.page.tabs.count(), 0)
        show_document(window)
        self.assertTrue(window.isWindow())  # Keep an explicitly detached document detached.
        self.page.attach(window); self.settle()
        self.assertFalse(window.isWindow())
        self.assertEqual(edit.text(), 'retained')
        show_document(window)
        self.assertEqual(self.page.tabs.count(), 1)

    def test_background_document_is_open_and_dialog_accept_removes_its_tab(self):
        first = qt.QDialog(); first.setWindowTitle('Metadata')
        second = qt.QMainWindow(); second.setWindowTitle('Reader')
        show_document(first); show_document(second); self.settle()
        self.assertFalse(first.isVisible())
        self.assertTrue(document_is_open(first))
        first.accept(); self.settle()
        self.assertEqual(self.page.tabs.count(), 1)
        self.assertFalse(document_is_open(first))

    def test_cancel_keeps_dirty_editor_and_detachment_preserves_its_buffer(self):
        from features.text_editor.window import EditorWindow
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            editor = EditorWindow(history_path=root/'recent.json', preferences_path=root/'preferences.ini')
            editor.current.editor.setPlainText('dirty buffer')
            editor.current.editor.document().setModified(True)
            show_document(editor); self.settle()
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Cancel):
                self.page.close_tab(0); self.settle()
                self.assertEqual(self.page.tabs.count(), 1)
                self.assertFalse(self.page.prepare_close())
                self.assertTrue(self.page.close_veto)
            self.page.detach_current(); self.page.attach(editor); self.settle()
            self.assertEqual(editor.current.editor.toPlainText(), 'dirty buffer')
            editor.current.editor.document().setModified(False)
            self.page.close_tab(0); self.settle()
            self.assertEqual(self.page.tabs.count(), 0)

    def test_closed_main_host_does_not_reopen_when_a_standalone_document_opens(self):
        self.host.hide()
        window = qt.QMainWindow()
        show_document(window)
        self.assertTrue(window.isWindow())
        self.assertEqual(self.page.tabs.count(), 0)
        window.close(); window.deleteLater()

    def test_embedded_epub_keeps_its_title_and_close_action_local(self):
        from books_fixture import make_book
        from features.books.reader import BookWindow
        from time import monotonic, sleep
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'sample.epub'; make_book(path)
            reader = BookWindow(path)
            show_document(reader)
            deadline = monotonic() + 5
            while reader.reader.worker is not None:
                self.assertLess(monotonic(), deadline); self.app.processEvents(); sleep(.005)
            self.assertIn('Sample Book', self.page.tabs.tabText(0))
            self.assertIs(reader.reader.reader_window(), reader)
            reader.reader.close_reader(); self.settle()
            self.assertEqual(self.page.tabs.count(), 0)
            self.assertTrue(self.host.isVisible())

    def test_embedded_comic_keys_are_scoped_to_the_reader(self):
        from io import BytesIO
        from zipfile import ZipFile
        from PIL import Image
        from features.comics.pages import ComicPages
        from features.comics.ui.reader import ComicReaderWindow
        from time import monotonic, sleep
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'sample.cbz'
            output = BytesIO(); Image.new('RGB', (20, 30), 'red').save(output, 'PNG')
            with ZipFile(path, 'w') as archive:
                for index in range(3): archive.writestr(f'{index}.png', output.getvalue())
            reader = ComicReaderWindow(ComicPages(path)); show_document(reader)
            deadline = monotonic() + 5
            while reader.busy or reader.page_cache.busy:
                self.assertLess(monotonic(), deadline); self.app.processEvents(); sleep(.005)
            with patch.object(reader, 'step') as step:
                event = qt.QKeyEvent(qt.QEvent.Type.KeyPress, qt.Qt.Key.Key_Right, qt.Qt.KeyboardModifier.NoModifier)
                reader.keys.eventFilter(reader.canvas, event)
                step.assert_called_once()
                step.reset_mock()
                unrelated = qt.QLineEdit(self.host)
                self.assertFalse(reader.keys.eventFilter(unrelated, event))
                step.assert_not_called()
            reader.close()
            while isValid(reader) and (reader.busy or reader.page_cache.busy):
                self.assertLess(monotonic(), deadline); self.app.processEvents(); sleep(.005)
            self.settle()
