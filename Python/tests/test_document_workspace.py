"""Embedded documents retain state, detach safely and protect dirty buffers on close."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from ui_new.documents import DocumentsPage, document_is_open, register_document_host, show_document
from shiboken6 import isValid


class DocumentWorkspaceTests(QtTestCase):
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
        self.assertTrue(self.page.records[window]['dock'].is_detached)
        self.assertEqual(self.page.attached_count, 0)
        show_document(window)
        self.assertTrue(self.page.records[window]['dock'].is_detached)  # Keep an explicitly detached document detached.
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
            second_window.close()
            self.settle()

    def test_reordered_document_tabs_close_the_visible_tab_and_list_in_order(self):
        first = qt.QMainWindow(); first.setWindowTitle('First')
        second = qt.QMainWindow(); second.setWindowTitle('Second')
        show_document(first); show_document(second); self.settle()
        bar = next(bar for bar in self.page.workspace.findChildren(qt.QTabBar)
                   if bar.parent() is self.page.workspace and bar.count() == 2)
        bar.moveTab(0, 1); self.settle()
        self.assertEqual([entry[1] for entry in self.page.document_entries()], ['Second', 'First'])
        self.page.close_tab(0); self.settle()
        self.assertTrue(document_is_open(first))
        self.assertFalse(document_is_open(second))

    def test_closed_document_retires_without_recreating_native_window_or_menu(self):
        document = qt.QMainWindow()
        document.menuBar().setNativeMenuBar(True)
        show_document(document); self.settle()
        self.page.records[document]['dock'].tab_header.close_button.click()
        self.settle()
        self.assertEqual(self.page.count, 0)
        self.assertFalse(document.isWindow())
        self.assertIs(document.parentWidget(), self.page)
        self.assertFalse(document.menuBar().isNativeMenuBar())
        self.assertFalse(document.isVisible())
        self.assertTrue(self.host.isVisible())

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
            self.assertEqual(self.page.attached_count, 1)
            self.assertTrue(document_is_open(editor))
            self.assertEqual(editor.current.editor.toPlainText(), 'dirty buffer')
            editor.current.editor.document().setModified(False)
            self.page.close_tab(0); self.settle()
            self.assertEqual(self.page.attached_count, 0)
            self.assertEqual(editor.service.windows, [])
            self.assertIsNone(editor.service.session.lock)

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
        dock.return_button.click(); self.settle()
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
        self.settle(); self.assertFalse(dock.is_detached)  # An ignored drag retains its owner.
        self.page.detach_current(); self.settle()
        self.assertTrue(dock.is_detached)
        point = self.page.workspace.contentsRect().center()
        mime = tab_mime(dock)
        event = qt.QDropEvent(qt.QPointF(point),qt.Qt.DropAction.MoveAction,mime,
                             qt.Qt.MouseButton.LeftButton,qt.Qt.KeyboardModifier.NoModifier)
        self.assertTrue(self.page.workspace.handle_tab_drop(self.page.workspace,event))
        self.settle(); self.assertFalse(dock.isFloating())
        self.assertEqual(edit.text(), 'retained')
        self.assertTrue(dock.tab_header.new_button.isVisible())

    def test_detached_plus_launches_document_in_its_own_container(self):
        from features import registry
        from features.contributions import DocumentLauncherContribution, RegisteredContribution
        first = qt.QMainWindow(); first.setWindowTitle('First')
        show_document(first); self.settle()
        self.page.detach_current(); self.settle()
        detached = self.page.records[first]['dock'].workspace
        created = []
        def new(parent):
            window = qt.QMainWindow(); window.setWindowTitle('Created here')
            created.append(window)
            return show_document(window)
        entry = RegisteredContribution('test', 'Test',
            DocumentLauncherContribution('test', 'Test editor', new, 'text', 0, new))
        choices = []
        menu = Mock()
        def submenu(title):
            sub = Mock(); actions = {}; choices.append(actions)
            sub.addAction.side_effect = lambda title, callback: actions.update({title: callback})
            return sub
        menu.addMenu.side_effect = submenu
        menu.exec.side_effect = lambda point: choices[0]['New']()
        with patch.object(registry, 'get_document_launchers', return_value=[entry]), \
                patch('ui_new.documents.qt.QMenu', return_value=menu):
            self.page.records[first]['dock'].local_new_button.click()
        self.settle()
        self.assertEqual(self.page.workspace.docks, [])
        self.assertEqual(len(detached.docks), 2)
        self.assertIs(detached.active_view.document, created[0])
        self.assertTrue(self.page.records[created[0]]['detached'])
        bar = next(bar for bar in detached.findChildren(qt.QTabBar) if bar.parent() is detached and bar.count() == 2)
        self.assertTrue(bar.isVisible())
        self.assertEqual(detached.window().windowTitle(), 'Documents: Created here')
        created[0].setWindowTitle('Renamed *'); self.settle()
        self.assertEqual(detached.window().windowTitle(), 'Documents: Renamed *')

    def test_async_session_restore_keeps_all_documents_in_originating_container(self):
        from time import monotonic, sleep
        from features.text_editor.document import Document
        from features.text_editor.session import document_record
        from features.text_editor.service import EditorService
        from commonUtils.persistence.session import SessionStore
        first = qt.QMainWindow(); show_document(first); self.settle()
        self.page.detach_current(); self.settle()
        detached = self.page.records[first]['dock'].workspace
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            records = []
            for text in ('First recovery', 'Second recovery'):
                document = Document(); document.editor.setPlainText(text)
                records.append(document_record(document)); document.deleteLater()
            checkpoint = root/'recovery.json'
            SessionStore(checkpoint).write({'version': 1, 'documents': records, 'active': 1})
            service = EditorService(self.page, history_path=root/'recent.json', preferences_path=root/'editor.ini')
            with patch.object(service.session, 'previous', return_value=checkpoint):
                placeholder = self.page.launch_document(detached, lambda parent: service.open())
            deadline = monotonic() + 5
            while placeholder.task.busy or len(service.windows) < 2:
                self.assertLess(monotonic(), deadline)
                self.app.processEvents(); sleep(.005)
            self.settle()
            self.assertEqual(self.page.workspace.docks, [])
            self.assertEqual(len(detached.docks), 3)
            self.assertEqual({window.current.editor.toPlainText() for window in service.windows},
                             {'First recovery', 'Second recovery'})
            self.assertTrue(all(self.page.records[window]['dock'].workspace is detached for window in service.windows))
            for window in tuple(service.windows):
                window.current.editor.document().setModified(False)
                window.close()
            first.close(); self.settle()

    def test_detached_text_creation_keeps_service_alive_after_return(self):
        from features.text_editor.service import EditorService
        from features.text_editor.contributions import new_document
        first = qt.QMainWindow(); show_document(first); self.settle()
        self.page.detach_current(); self.settle()
        detached = self.page.records[first]['dock'].workspace
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            service = EditorService(self.page, history_path=root/'recent.json', preferences_path=root/'editor.ini')
            self.page._text_editor_service = service
            editor = self.page.launch_document(detached, new_document); self.settle()
            self.assertIs(editor.service, service)
            self.assertIs(service.parent(), self.page)
            dock = self.page.records[editor]['dock']
            self.page.workspace.adopt(self.page.records[first]['dock']); self.settle()
            dock.return_button.click(); self.settle()
            self.assertTrue(isValid(service))
            self.assertIs(dock.workspace, self.page.workspace)
            self.assertIs(editor.service, service)
            self.assertEqual(self.page.workspace.detached_windows, [])
            editor.close(); first.close(); self.settle()

    def test_cancelled_detached_creation_and_container_close_preserve_documents(self):
        window = qt.QMainWindow(); window.setCentralWidget(qt.QLineEdit('Retained'))
        show_document(window); self.settle()
        self.page.detach_current(); self.settle()
        dock = self.page.records[window]['dock']; detached = dock.workspace
        self.assertIsNone(self.page.launch_document(detached, lambda parent: None))
        self.assertEqual(detached.docks, [dock])
        self.assertIsNone(self.page._creation_workspace)
        detached.window().close(); self.settle()
        self.assertIs(dock.workspace, self.page.workspace)
        self.assertEqual(self.page.attached_count, 1)
        self.assertEqual(window.centralWidget().text(), 'Retained')

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


class PublicCloseContractTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def test_pending_owner_does_not_need_private_worker_attributes(self):
        from commonUtils.ui.document_host import CloseOutcome
        host = qt.QMainWindow()
        page = DocumentsPage(lambda: None, host)
        window = qt.QMainWindow()
        window.request_close = lambda: CloseOutcome.PENDING
        page.present(window)
        self.assertFalse(page.prepare_close())
        self.assertFalse(page.close_veto)
        window.request_close = lambda: CloseOutcome.VETOED
        self.assertFalse(page.prepare_close())
        self.assertTrue(page.close_veto)
        window.request_close = lambda: CloseOutcome.ACCEPTED
        self.assertTrue(page.prepare_close())
        host.close()
        host.deleteLater()
