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
        self.assertEqual(self.page.attached_count, 1)
        self.page.detach_current(); self.settle()
        self.assertTrue(self.page.records[window]['dock'].isFloating())
        self.assertEqual(self.page.attached_count, 0)
        show_document(window)
        self.assertTrue(self.page.records[window]['dock'].isFloating())  # Keep an explicitly detached document detached.
        self.page.attach(window); self.settle()
        self.assertFalse(window.isWindow())
        self.assertEqual(edit.text(), 'retained')
        show_document(window)
        self.assertEqual(self.page.attached_count, 1)

    def test_text_files_use_separate_host_tabs_without_inner_tabs_or_untitled_buffers(self):
        from features.text_editor.service import EditorService
        from time import monotonic, sleep
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / 'first.txt'; first.write_text('First')
            second = root / 'second.txt'; second.write_text('Second')
            service = EditorService(self.app, history_path=root/'recent.json', preferences_path=root/'editor.ini')
            first_window = service.open(first)
            second_window = service.open(second)
            self.assertIs(service.open(first), first_window)
            deadline = monotonic() + 5
            while any(window.task.busy for window in service.windows):
                self.assertLess(monotonic(), deadline)
                self.app.processEvents(); sleep(.005)
            self.settle()
            self.assertEqual(self.page.attached_count, 2)
            for window, path in ((first_window, first), (second_window, second)):
                self.assertEqual(len(window.documents), 1)
                self.assertEqual(window.current.path, path.resolve())
                self.assertEqual(window.findChildren(qt.QTabWidget), [])
            self.assertTrue(all(tab is None for window, title, tab, detached in self.page.document_entries()))
            self.page.records[first_window]['dock'].tab_header.close_button.click()
            self.settle()
            self.assertEqual(self.page.count, 1)
            self.assertEqual(service.windows, [second_window])
            self.assertTrue(self.host.isVisible())
            self.assertEqual(second_window.current.editor.toPlainText(), 'Second')

    def test_background_document_is_open_and_dialog_accept_removes_its_tab(self):
        first = qt.QDialog(); first.setWindowTitle('Metadata')
        second = qt.QMainWindow(); second.setWindowTitle('Reader')
        show_document(first); show_document(second); self.settle()
        self.assertIs(self.page.workspace.active_view.document, second)
        self.assertIn(self.page.records[first]['dock'],
                      self.page.workspace.tabifiedDockWidgets(self.page.records[second]['dock']))
        self.assertTrue(document_is_open(first))
        first.accept(); self.settle()
        self.assertEqual(self.page.attached_count, 1)
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
                self.assertEqual(self.page.attached_count, 1)
                self.assertFalse(self.page.prepare_close())
                self.assertTrue(self.page.close_veto)
            self.page.detach_current(); self.page.attach(editor); self.settle()
            self.assertEqual(editor.current.editor.toPlainText(), 'dirty buffer')
            editor.current.editor.document().setModified(False)
            self.page.close_tab(0); self.settle()
            self.assertEqual(self.page.attached_count, 0)

    def test_origin_controller_leaves_hosted_document_alive(self):
        from features.books.controller import BooksController
        window = qt.QMainWindow(); window.setWindowTitle('Retained reader')
        window.prepare_close = lambda: True
        controller = BooksController(self.host)
        controller.windows.append(window)
        show_document(window); self.settle()
        self.assertTrue(controller.prepare_close())
        self.assertTrue(document_is_open(window))
        self.assertTrue(window.isVisible())
        self.page.closing = True
        self.assertTrue(controller.prepare_close()); self.settle()
        self.assertFalse(document_is_open(window))

    def test_epub_survives_deleted_origin_controller_and_closes_from_its_tab(self):
        from books_fixture import make_book
        from features.books.controller import BooksController
        from time import monotonic, sleep
        with TemporaryDirectory() as temporary:
            path = Path(temporary)/'sample.epub'; make_book(path)
            origin = qt.QWidget()
            controller = BooksController(origin)
            document = controller.open(path)
            deadline = monotonic() + 5
            while document.reader.worker is not None:
                self.assertLess(monotonic(), deadline); self.app.processEvents(); sleep(.005)
            self.assertTrue(controller.prepare_close())
            origin.deleteLater()
            self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
            self.assertFalse(isValid(controller))
            self.page.records[document]['dock'].tab_header.close_button.click()
            self.settle()
            self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
            self.assertEqual(self.page.count, 0)
            self.assertTrue(self.host.isVisible())

    def test_closed_main_host_does_not_reopen_when_a_standalone_document_opens(self):
        self.host.hide()
        window = qt.QMainWindow()
        show_document(window)
        self.assertTrue(window.isWindow())
        self.assertEqual(self.page.attached_count, 0)
        window.close(); window.deleteLater()

    def test_all_detached_documents_can_return_from_their_window(self):
        window = qt.QMainWindow(); window.setWindowTitle('Detached reader')
        show_document(window); self.settle()
        self.page.detach_current(); self.settle()
        self.assertEqual(self.page.attached_count, 0)
        self.assertEqual(self.page.count, 1)
        dock = self.page.records[window]['dock']
        from PySide6.QtTest import QTest
        QTest.mouseDClick(dock.tab_header, qt.Qt.MouseButton.LeftButton); self.settle()
        self.assertEqual(self.page.attached_count, 1)
        self.assertFalse(window.isWindow())
        self.assertFalse(dock.isFloating())
        self.assertNotIn('return_control', self.page.records[window])

    def test_document_tabs_drag_with_full_pane_preview_and_drop_back(self):
        from commonUtils.ui.workspace_drag import tab_mime
        window = qt.QMainWindow(); window.setWindowTitle('Dragged reader')
        edit = qt.QLineEdit('retained'); window.setCentralWidget(edit)
        show_document(window); self.settle()
        dock = self.page.records[window]['dock']
        with patch('commonUtils.ui.workspace_drag.qt.QDrag') as drag, \
             patch.object(qt.QCursor, 'pos', return_value=qt.QPoint(5000,5000)), \
             patch.object(qt.QApplication, 'mouseButtons', return_value=qt.Qt.MouseButton.NoButton):
            drag.return_value.exec.return_value = qt.Qt.DropAction.IgnoreAction
            self.page.workspace.drag_tab(dock)
            preview = drag.return_value.setPixmap.call_args.args[0]
            self.assertGreater(preview.width(), 300)
            self.assertGreater(preview.height(), 200)
        self.settle(); self.assertTrue(dock.isFloating())
        point = self.page.workspace.contentsRect().center()
        mime = tab_mime(dock)
        event = qt.QDropEvent(qt.QPointF(point),qt.Qt.DropAction.MoveAction,mime,
                             qt.Qt.MouseButton.LeftButton,qt.Qt.KeyboardModifier.NoModifier)
        self.assertTrue(self.page.workspace.handle_tab_drop(self.page.workspace,event))
        self.settle(); self.assertFalse(dock.isFloating())
        self.assertEqual(edit.text(), 'retained')
        self.assertFalse(dock.tab_header.new_button.isVisible())

    def test_readers_can_split_and_browser_tabs_keep_their_own_workspace(self):
        from commonUtils.ui.workspace import Workspace
        from commonUtils.ui.workspace_drag import tab_mime
        first = qt.QMainWindow(); second = qt.QMainWindow()
        show_document(first); show_document(second); self.settle()
        left = self.page.records[first]['dock']; right = self.page.records[second]['dock']
        self.page.workspace.arrange(right,'right',anchor=left); self.settle()
        self.assertLess(left.geometry().right(), right.geometry().left())
        self.assertTrue(first.isVisible() and second.isVisible())
        show_document(second); self.settle()
        self.assertFalse(self.page.workspace.tabifiedDockWidgets(right))
        browser = Workspace(lambda argument: qt.QWidget(), self.host)
        browser.add_view(); self.addCleanup(browser.deleteLater)
        mime = tab_mime(right)
        event = qt.QDropEvent(qt.QPointF(50,50),qt.Qt.DropAction.MoveAction,mime,
                             qt.Qt.MouseButton.LeftButton,qt.Qt.KeyboardModifier.NoModifier)
        self.assertFalse(browser.handle_tab_drop(browser,event))

    def test_markdown_uses_workspace_and_close_cancel_vetoes_main_close(self):
        from commonUtils.ui.markdown import open_markdown
        with TemporaryDirectory() as temporary:
            path = Path(temporary)/'note.md'; path.write_text('# A note')
            window = open_markdown(path, allow_edit=True); self.settle()
            self.assertFalse(window.isWindow())
            self.assertEqual(self.page.attached_count, 1)
            with patch.object(window.viewer, 'can_close', return_value=False):
                self.assertFalse(self.page.prepare_close())
                self.assertTrue(self.page.close_veto)
            window.close(); self.settle()

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
            self.assertIn('Sample Book', self.page.records[reader]['dock'].windowTitle())
            self.assertIs(reader.reader.reader_window(), reader)
            reader.reader.close_reader(); self.settle()
            self.assertEqual(self.page.attached_count, 0)
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
