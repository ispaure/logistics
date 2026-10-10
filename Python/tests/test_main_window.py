"""Main navigation startup and feature page lifecycle."""

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import Mock, patch
import unittest
from commonUtils.tests.qt_test_case import QtTestCase

from commonUtils.ui import pyside as qt
from features.contributions import PageContribution, RegisteredContribution
from ui_new import main_window


class MainWindowTests(QtTestCase):
    def test_notification_footer_releases_space_when_empty(self):
        from ui_new.notifications import notify
        from uuid import uuid4
        window = self.window(); window.dlg.show(); self.app.processEvents()
        self.assertTrue(window.dlg.statusBar().isHidden())
        notify('test', 'Completed', 'Navigation check', identifier=uuid4().hex)
        self.app.processEvents()
        self.assertFalse(window.dlg.statusBar().isHidden())
        self.assertTrue(window.toast.isVisible())
        window.toast.timer.timeout.emit(); self.app.processEvents()
        self.assertTrue(window.dlg.statusBar().isHidden())

    def test_named_feature_destinations_are_ordered_and_debug_has_a_footer_button(self):
        entries = [RegisteredContribution(icon, name, PageContribution(name, icon, self.page,
                   order=order, navigation_icon=icon))
                   for icon, name, order in [('links', 'Links', 20), ('aviation', 'Aviation Tools', 10),
                                              ('smart_home', 'Smart Home', 30)]]
        window = self.window(entries); window.dlg.show(); self.app.processEvents()
        rail = window.sidebar
        self.assertEqual([rail.feature_destinations.itemAt(i).widget().text() for i in range(3)],
                         ['Smart Home', 'Aviation Tools', 'Links'])
        self.assertEqual(rail.tools_menu.actions(), [])
        self.assertTrue(rail.buttons['tools'].isHidden())
        self.assertTrue(rail.buttons['debug'].isVisible())
        rail.buttons['debug'].click()
        self.assertIs(window.tabs.currentWidget(), rail.pages['debug'])
        for button in (rail.feature_destinations.itemAt(i).widget() for i in range(3)):
            self.assertTrue(button.isVisible())
            button.click()
            self.assertTrue(button.isChecked())

    def test_abandoned_docking_preview_restores_page_and_destination(self):
        from commonUtils.ui.document_host import show_document
        window = self.window(); window.dlg.show()
        document = qt.QMainWindow(); document.setCentralWidget(qt.QLabel('Document'))
        show_document(document)
        dock = window.documents.records[document]['dock']
        dock.setFloating(True)
        previous = window._core_pages[0][2]
        window.tabs.setCurrentWidget(previous)
        before = window._last_destination
        from commonUtils.ui.workspace_drag import NativeWindowDrag
        container = dock.window()
        drag = NativeWindowDrag(container, container.geometry())
        container._native_drag = drag
        point = window.dlg.frameGeometry().center()
        drag.move(point)
        self.assertIs(window.tabs.currentWidget(), window.documents)
        drag.finish(point, cancel=True)
        self.assertIs(window.tabs.currentWidget(), previous)
        self.assertIs(window._last_destination, before)
        self.assertTrue(dock.workspace.is_detached)
        document.close()

    def test_floating_document_mouse_drop_reveals_documents_and_splits_beside_its_neighbor(self):
        from commonUtils.ui.document_host import show_document
        window = self.window(); window.dlg.show(); window.dlg.activateWindow()
        first = qt.QMainWindow(); first.setCentralWidget(qt.QLineEdit('Keep this content'))
        second = qt.QMainWindow(); second.setCentralWidget(qt.QLabel('Neighbor'))
        show_document(first); show_document(second)
        for _ in range(5): self.app.processEvents()
        workspace = window.documents.workspace
        dock = window.documents.records[first]['dock']
        dock.setFloating(True)
        window.tabs.setCurrentWidget(window._core_pages[0][2])
        self.app.processEvents()
        header = dock.tab_header
        def mouse(kind, point):
            button = qt.Qt.MouseButton.LeftButton
            event = qt.QMouseEvent(kind, qt.QPointF(header.mapFromGlobal(point)), qt.QPointF(point),
                button if kind != qt.QEvent.Type.MouseMove else qt.Qt.MouseButton.NoButton,
                button if kind != qt.QEvent.Type.MouseButtonRelease else qt.Qt.MouseButton.NoButton,
                qt.Qt.KeyboardModifier.NoModifier)
            self.app.sendEvent(header, event)
            for _ in range(5): self.app.processEvents()
        origin = header.mapToGlobal(header.rect().center())
        mouse(qt.QEvent.Type.MouseButtonPress, origin)
        point = workspace.mapToGlobal(qt.QPoint(workspace.width() - 3, workspace.height() // 2))
        mouse(qt.QEvent.Type.MouseMove, point)
        mouse(qt.QEvent.Type.MouseButtonRelease, point)
        neighbor = window.documents.records[second]['dock']
        self.assertIs(window.tabs.currentWidget(), window.documents)
        self.assertFalse(dock.isFloating())
        self.assertNotIn(neighbor, workspace.tabifiedDockWidgets(dock))
        self.assertGreater(dock.x(), neighbor.x())
        self.assertEqual(first.centralWidget().text(), 'Keep this content')
        first.close(); second.close(); self.app.processEvents()

    def test_document_x_closes_only_its_document_attached_or_floating(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from commonUtils.ui.markdown import open_markdown
        window = self.window(); window.dlg.show()
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'note.md'; path.write_text('# Note')
            for floating in (False, True):
                document = open_markdown(path)
                for _ in range(5): self.app.processEvents()
                dock = window.documents.records[document]['dock']
                if floating:
                    dock.setFloating(True)
                for _ in range(5): self.app.processEvents()
                with patch.object(window, 'can_close', wraps=window.can_close) as close_main:
                    dock.tab_header.close_button.click()
                    for _ in range(10): self.app.processEvents()
                    close_main.assert_not_called()
                self.assertTrue(window.dlg.isVisible())
                self.assertFalse(window._closing)
                self.assertEqual(window.documents.count, 0)
                self.assertEqual(window.documents.workspace.docks, [])

    def test_actual_epub_and_comic_x_never_close_the_application(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from time import monotonic, sleep
        from io import BytesIO
        from zipfile import ZipFile
        from PIL import Image
        from books_fixture import make_book
        from features.books.reader import BookWindow
        from features.comics.pages import ComicPages
        from features.comics.ui.reader import ComicReaderWindow
        from commonUtils.ui.document_host import show_document
        from PySide6.QtTest import QTest, QSignalSpy
        from shiboken6 import isValid
        window = self.window(); window.dlg.show()
        quit_signal = QSignalSpy(self.app.lastWindowClosed)
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            epub = root/'sample.epub'; make_book(epub)
            comic = root/'sample.cbz'
            output = BytesIO(); Image.new('RGB', (20, 30), 'red').save(output, 'PNG')
            with ZipFile(comic, 'w') as archive:
                archive.writestr('page.png', output.getvalue())
            for floating in (False, True):
                for create in (lambda: BookWindow(epub), lambda: ComicReaderWindow(ComicPages(comic))):
                    document = create(); show_document(document)
                    deadline = monotonic() + 5
                    while (getattr(getattr(document, 'reader', None), 'worker', None) is not None
                           or getattr(document, 'busy', False) or getattr(getattr(document, 'page_cache', None), 'busy', False)):
                        self.assertLess(monotonic(), deadline)
                        self.app.processEvents(); sleep(.005)
                    dock = window.documents.records[document]['dock']
                    if floating: dock.setFloating(True)
                    for _ in range(5): self.app.processEvents()
                    with patch.object(window, 'can_close', wraps=window.can_close) as close_main, \
                         patch.object(document, 'close', wraps=document.close) as native_close:
                        QTest.mouseClick(dock.tab_header.close_button, qt.Qt.MouseButton.LeftButton)
                        native_close.assert_not_called()
                        while window.documents.count:
                            self.assertLess(monotonic(), deadline)
                            self.app.processEvents(); sleep(.005)
                        for _ in range(10): self.app.processEvents()
                        close_main.assert_not_called()
                    self.assertTrue(window.dlg.isVisible())
                    self.assertFalse(window._closing)
                    self.assertEqual(quit_signal.count(), 0)
                    self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
                    self.assertFalse(isValid(document))
            # Exercise the actual native grouped-tab X too, keeping a second reader open.
            book = BookWindow(epub); show_document(book)
            reader = ComicReaderWindow(ComicPages(comic)); show_document(reader)
            deadline = monotonic() + 5
            while book.reader.worker is not None or reader.busy or reader.page_cache.busy:
                self.assertLess(monotonic(), deadline); self.app.processEvents(); sleep(.005)
            for _ in range(5): self.app.processEvents()
            workspace = window.documents.workspace
            bar = next(bar for bar in workspace.findChildren(qt.QTabBar)
                       if bar.parent() is workspace and bar.count())
            dock = window.documents.records[reader]['dock']
            index = next(i for i in range(bar.count()) if workspace._tab_dock(bar, i) is dock)
            with patch.object(window, 'can_close', wraps=window.can_close) as close_main:
                QTest.mouseClick(bar.tabButton(index, qt.QTabBar.ButtonPosition.LeftSide), qt.Qt.MouseButton.LeftButton)
                for _ in range(10): self.app.processEvents()
                self.assertEqual(window.documents.count, 1)
                self.assertTrue(isValid(book))
                window.documents.records[book]['dock'].tab_header.close_button.click()
                for _ in range(10): self.app.processEvents()
                close_main.assert_not_called()
            self.assertTrue(window.dlg.isVisible())
            self.assertEqual(quit_signal.count(), 0)

    def test_grouped_document_x_closes_clicked_document_then_last_document(self):
        from commonUtils.ui.document_host import show_document
        from PySide6.QtTest import QTest
        window = self.window(); window.dlg.show()
        first = qt.QMainWindow(); first.setCentralWidget(qt.QLineEdit('First'))
        second = qt.QMainWindow(); second.setCentralWidget(qt.QLineEdit('Second'))
        show_document(first); show_document(second)
        for _ in range(5): self.app.processEvents()
        workspace = window.documents.workspace
        dock = window.documents.records[first]['dock']
        bar = next(bar for bar in workspace.findChildren(qt.QTabBar)
                   if bar.parent() is workspace and bar.count())
        index = next(i for i in range(bar.count()) if workspace._tab_dock(bar, i) is dock)
        button = bar.tabButton(index, qt.QTabBar.ButtonPosition.LeftSide)
        with patch.object(window, 'can_close', wraps=window.can_close) as close_main:
            QTest.mouseClick(button, qt.Qt.MouseButton.LeftButton)
            for _ in range(10): self.app.processEvents()
            self.assertEqual(window.documents.count, 1)
            self.assertTrue(second.isVisible())
            self.assertEqual(second.centralWidget().text(), 'Second')
            window.documents.records[second]['dock'].tab_header.close_button.click()
            for _ in range(10): self.app.processEvents()
            close_main.assert_not_called()
        self.assertTrue(window.dlg.isVisible())
        self.assertEqual(window.documents.count, 0)
        first.deleteLater(); second.deleteLater()

    def test_browser_x_keeps_last_tab_and_closes_only_clicked_neighbor(self):
        from PySide6.QtTest import QTest
        window = self.browser_window(); page = window.tabs.widget(0)
        self.wait_browser(page)
        workspace = page.workspace
        first = workspace.active_dock
        self.assertTrue(workspace.keep_one_tab)
        self.assertFalse(first.close())
        workspace.add_view(); self.wait_browser(page)
        workspace._refresh_tab_headers()
        bar = next(bar for bar in workspace.findChildren(qt.QTabBar)
                   if bar.parent() is workspace and bar.count())
        index = next(i for i in range(bar.count()) if workspace._tab_dock(bar, i) is first)
        QTest.mouseClick(bar.tabButton(index, qt.QTabBar.ButtonPosition.LeftSide), qt.Qt.MouseButton.LeftButton)
        for _ in range(10): self.app.processEvents()
        self.assertEqual(len(workspace.docks), 1)
        self.assertFalse(workspace.active_dock.close())
        self.assertTrue(window.dlg.isVisible())
        self.assertFalse(window._closing)

    def test_sync_job_appears_in_the_rail_and_marks_background_completion(self):
        import sys, time
        from commonUtils.ui.process_progress import open_process
        window = self.window()
        window.dlg.show(); window.dlg.activateWindow()
        with patch.object(window.actions, 'notify') as notice:
            job = open_process('Sync', sys.executable, ['-c', 'import time; time.sleep(.1)'],
                               context={'operation': 'Sync'})
            browser = window._core_pages[0][2]
            window.tabs.setCurrentWidget(browser)
            deadline = time.monotonic() + 5
            while job.result is None:
                self.assertLess(time.monotonic(), deadline)
                self.app.processEvents(); time.sleep(.005)
            self.app.processEvents()
            self.assertTrue(window.sidebar.buttons['actions'].isVisible())
            self.assertEqual(window.sidebar.buttons['actions'].unread, 1)
            with patch.object(main_window.registry, 'get_pages', return_value=[]):
                window._sync_feature_pages()
            self.assertGreaterEqual(window.tabs.indexOf(window.actions), 0)
            window.sidebar.buttons['actions'].click(); self.app.processEvents()
            self.assertIs(window.tabs.currentWidget(), window.actions)
            self.assertEqual(window.sidebar.buttons['actions'].unread, 0)
            notice.assert_called_once()
            job.close(); self.app.processEvents()
            self.assertEqual(window.actions.count, 0)
            self.assertFalse(window.sidebar.buttons['actions'].isVisible())

    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.pages = []

    def page(self, parent=None):
        page = qt.QWidget(parent)
        page.refresh = Mock()
        self.pages.append(page)
        return page

    def contribution(self, name, page_id, order=50):
        return RegisteredContribution(
            'feature', 'Feature', PageContribution(name, page_id, self.page, order)
        )

    def window(self, contributions=()):
        with patch.object(main_window, 'CORE_TABS', (
                (0, 'Folders', self.page), (100, 'Debug', self.page))), patch.object(
                main_window.registry, 'get_pages', return_value=contributions):
            window = main_window.MainWindow()
        self.addCleanup(window.dlg.deleteLater)
        return window

    def test_feature_destination_button_selects_page_and_survives_toggle(self):
        contribution = RegisteredContribution('private', 'Private', PageContribution(
            'Private page', 'private.main', self.page, order=20, navigation_icon='controller'))
        window = self.window([contribution])
        feature_page = window._feature_pages[('private', 'private.main')]
        key = next(iter(window.sidebar.feature_buttons))
        button = window.sidebar.buttons[key]
        self.assertFalse(button.isHidden())
        self.assertNotIn('Private page', [action.text() for action in window.sidebar.tools_menu.actions()])
        button.click()
        self.assertIs(window.tabs.currentWidget(), feature_page)
        self.assertTrue(button.isChecked())
        with patch.object(main_window.registry, 'get_pages', return_value=[]):
            window._sync_feature_pages()
        self.assertTrue(button.isHidden())
        with patch.object(main_window.registry, 'get_pages', return_value=[contribution]):
            window._sync_feature_pages()
        self.assertFalse(button.isHidden())
        self.assertIs(window.sidebar.buttons[key], button)
        self.assertEqual(len(window.sidebar.feature_buttons), 1)

    def test_startup_failure_waits_for_previously_created_worker(self):
        class WorkingPage(qt.QWidget):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.worker = qt.QThread(self)
                self.worker.run = lambda: self.worker.msleep(40)
                self.worker.start()

            def prepare_close(self):
                self.worker.requestInterruption()
                return not self.worker.isRunning()

        created = []
        def working(parent=None):
            page = WorkingPage(parent)
            created.append(page)
            return page
        def failing(parent=None):
            raise RuntimeError('folder discovery failed')
        with patch.object(main_window, 'CORE_TABS', ((0,'Browser',working),(5,'Folders',failing))), \
                patch.object(main_window.registry, 'get_pages', return_value=[]):
            with self.assertRaisesRegex(RuntimeError, 'folder discovery failed'):
                main_window.MainWindow()
        self.assertEqual(len(created), 1)
        self.assertFalse(created[0].worker.isRunning())

    def test_real_core_pages_start_with_rclone_contributions(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from features import rclone
        from features.rclone import credentials
        from services import folder_sources
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'example.txt').write_text('fixture')
            original = main_window.CORE_TABS
            core = ((0,'File Browser',lambda parent: main_window.FileBrowserPage(parent,root_path=root)),) + original[1:]
            with patch.object(main_window.registry,'get_enabled_features',return_value=[rclone]), \
                    patch.object(credentials,'get_loaded_credential_config_paths',return_value=[]), \
                    patch.object(folder_sources,'get_folder_entries',return_value=[]), \
                    patch.object(main_window,'CORE_TABS',core):
                window = main_window.MainWindow()
                self.assertEqual([window.tabs.tabText(i) for i in range(window.tabs.count())],
                                 ['File Browser','Folder Hub','Settings','Debug'])
                # Drain the application's event queue, including completion
                # callbacks queued before entering a nested test event loop.
                from time import monotonic, sleep
                deadline = monotonic() + 5
                while not window.can_close() and monotonic() < deadline:
                    self.app.processEvents(); sleep(.005)
                browser = window.tabs.widget(0).file_browser
                self.assertTrue(window.can_close(), repr({
                    'listing': browser.busy, 'index': browser.folder_busy,
                    'cover': browser.views.cover_busy, 'storage': browser.views.storage.busy,
                    'actions': browser.file_actions.busy,
                    'pages': [(name,getattr(page,'can_close',lambda:True)(),
                               getattr(page,'prepare_close',lambda:True)())
                              for _,name,page in window._core_pages],
                }))
                window.dlg.close()
                window.dlg.deleteLater()

    def test_startup_constructs_each_page_once_without_redundant_refresh(self):
        window = self.window([self.contribution('Feature', 'feature')])
        self.assertEqual(len(self.pages), 3)
        self.assertEqual([window.tabs.tabText(index) for index in range(3)],
                         ['Folders', 'Feature', 'Debug'])
        for page in self.pages:
            page.refresh.assert_not_called()
        window.tabs.setCurrentIndex(1)
        window.tabs.currentWidget().refresh.assert_called_once_with()
        window.tabs.setCurrentIndex(2)
        window.tabs.currentWidget().refresh.assert_called_once_with()
        window.tabs.setCurrentIndex(0)
        window.tabs.currentWidget().refresh.assert_called_once_with()

    def test_persistent_document_tree_groups_editors_and_keeps_utility_entry(self):
        from features.contributions import DocumentLauncherContribution
        from commonUtils.ui.document_host import show_document
        opener = Mock()
        launcher = RegisteredContribution('text_editor', 'Text Editor',
            DocumentLauncherContribution('text', 'Text Editor', opener, 'text'))
        with patch.object(main_window.registry, 'get_document_launchers', return_value=[launcher]):
            window = self.window(); window.dlg.show(); window._refresh_sidebar()
            window.sidebar.show_documents()
            self.assertTrue(window.sidebar.document_tree.isVisible())
            self.assertTrue(window.sidebar.buttons['documents'].isVisible())
            self.assertTrue(window.sidebar.bulk_rename_button.isVisible())
            window.sidebar.editor_buttons['text'].click()
            opener.assert_called_once_with(window.documents)
            first = qt.QMainWindow(); first.document_editor_id = 'text'; first.setWindowTitle('notes.txt')
            second = qt.QMainWindow(); second.document_editor_id = 'markdown'; second.setWindowTitle('guide.md')
            show_document(first); show_document(second); self.app.processEvents()
            groups = window.sidebar.editor_groups
            self.assertEqual(groups['text'].child(0).text(0), 'notes.txt')
            self.assertEqual(groups['markdown'].child(0).text(0), 'guide.md')
            window.sidebar.document_tree.itemClicked.emit(groups['text'].child(0), 0)
            self.assertIs(window.documents.workspace.active_view.document, first)
            first.close(); second.close(); self.app.processEvents()
            self.assertEqual(window.documents.count, 0)
            window.sidebar.show_documents()
            self.assertTrue(window.sidebar.document_tree.isVisible())
            self.assertIn('text', window.sidebar.editor_groups)
            window.dlg.close()

    def test_document_overlay_new_open_and_cancel_keep_current_page(self):
        from features.contributions import DocumentLauncherContribution
        opener, creator = Mock(), Mock()
        launcher = RegisteredContribution('text_editor', 'Text Editor',
            DocumentLauncherContribution('text', 'Text Editor', opener, 'text', 10, creator))
        with patch.object(main_window.registry, 'get_document_launchers', return_value=[launcher]):
            window = self.window(); window.dlg.show(); window._refresh_sidebar()
            current = window.tabs.currentWidget()
            self.assertFalse(window.sidebar.document_overlay.isVisible())
            self.assertFalse(window.sidebar.buttons['documents'].isChecked())
            window.sidebar.show_documents()
            self.assertTrue(window.sidebar.document_overlay.isVisible())
            self.assertTrue(window.sidebar.buttons['documents'].isChecked())
            self.assertIs(window.tabs.currentWidget(), current)
            button = window.sidebar.editor_buttons['text']
            self.assertIsNone(button.menu())
            group = window.sidebar.editor_groups['text']
            self.assertFalse(group.flags() & qt.Qt.ItemFlag.ItemIsSelectable)
            row = window.sidebar.document_tree.itemWidget(group, 0)
            self.assertEqual([item.text() for item in row.findChildren(qt.QToolButton)], ['New', 'Open…'])
            from PySide6.QtTest import QTest
            for passive in row.findChildren(qt.QLabel):
                QTest.mouseClick(passive, qt.Qt.MouseButton.LeftButton)
            creator.assert_not_called()
            opener.assert_not_called()
            self.assertTrue(window.sidebar.document_overlay.isVisible())
            self.assertTrue(group.isExpanded())
            QTest.mouseClick(window.sidebar.editor_new_buttons['text'], qt.Qt.MouseButton.LeftButton)
            creator.assert_called_once_with(window.documents)
            opener.assert_not_called()
            self.assertFalse(window.sidebar.document_overlay.isVisible())
            self.assertFalse(window.sidebar.buttons['documents'].isChecked())
            window.sidebar.show_documents()
            QTest.mouseClick(window.sidebar.editor_buttons['text'], qt.Qt.MouseButton.LeftButton)
            opener.assert_called_once_with(window.documents)
            self.assertIs(window.tabs.currentWidget(), current)
            window.sidebar.show_documents(); window.sidebar.show_documents()
            self.assertFalse(window.sidebar.document_overlay.isVisible())
            window.sidebar.show_documents()
            from PySide6.QtTest import QTest
            QTest.keyClick(window.sidebar.document_tree, qt.Qt.Key.Key_Escape)
            self.app.processEvents()
            self.assertFalse(window.sidebar.document_overlay.isVisible())
            window.dlg.close()

    def test_sidebar_groups_tools_and_keeps_documents_when_features_change(self):
        from ui_new.documents import show_document
        contribution = self.contribution('Calculator', 'calculator')
        window = self.window([contribution]); window.dlg.show(); self.app.processEvents()
        self.assertTrue(window.tabs.tabBar().isHidden())
        self.assertEqual(window.sidebar.width(), 60)
        self.assertEqual([action.text() for action in window.sidebar.tools_menu.actions()], ['Calculator'])
        self.assertTrue(window.sidebar.buttons['debug'].isVisible())
        self.assertFalse(window.sidebar.tools_menu.isVisible())
        reader = qt.QMainWindow(); reader.setWindowTitle('Open reader')
        show_document(reader); self.app.processEvents()
        self.assertIs(window.tabs.currentWidget(), window.documents)
        self.assertFalse(reader.isWindow())
        with patch.object(main_window.registry, 'get_pages', return_value=[]):
            window._sync_feature_pages()
        self.assertIs(window.tabs.currentWidget(), window.documents)
        self.assertTrue(window.sidebar.buttons['documents'].isChecked())
        window.sidebar.show_documents()
        self.assertEqual(sum(item.childCount() for item in window.sidebar.editor_groups.values()), 1)
        reader.close(); self.app.processEvents()
        window.dlg.close(); self.app.processEvents()

    def test_pages_with_equal_order_sort_by_display_name(self):
        window = self.window([self.contribution('Zebra', 'zebra'),
                              self.contribution('apple', 'apple')])
        self.assertEqual([window.tabs.tabText(index) for index in range(4)],
                         ['Folders', 'apple', 'Zebra', 'Debug'])

    def test_duplicate_page_ids_fail_before_any_factory_runs(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate contributed page ID: same'):
            self.window([self.contribution('One', 'same'),
                         self.contribution('Two', 'same')])
        self.assertEqual(self.pages, [])

    def test_pages_without_refresh_and_empty_navigation_are_safe(self):
        window = self.window()
        plain_page = qt.QWidget(window.dlg)
        window.tabs.addTab(plain_page, 'Plain')
        window.tabs.setCurrentWidget(plain_page)
        window.tabs.clear()
        self.assertIsNone(window.tabs.currentWidget())

    def test_feature_pages_hide_and_restore_without_recreating_or_deleting(self):
        from shiboken6 import isValid
        contribution = self.contribution('Feature', 'feature')
        window = self.window([contribution])
        feature_page = window.tabs.widget(1)
        window.tabs.setCurrentWidget(feature_page)
        with patch.object(main_window.registry, 'get_pages', return_value=[]):
            window._sync_feature_pages()
        self.assertEqual(window.tabs.count(), 2)
        self.assertEqual(window.tabs.indexOf(feature_page), -1)
        self.assertTrue(isValid(feature_page))
        with patch.object(main_window.registry, 'get_pages', return_value=[contribution]):
            window._sync_feature_pages()
        self.assertIs(window.tabs.widget(1), feature_page)
        self.assertEqual(len(self.pages), 3)

    def browser_window(self, extensions=()):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from ui_new.file_browser import FileBrowserPage
        self.temporary = TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / 'file.txt').write_text('fixture')
        with patch.object(main_window, 'CORE_TABS', ((0, 'File Browser', FileBrowserPage),
                (5, 'Folder Hub', self.page), (90, 'Settings', self.page))), patch.object(
                main_window.registry, 'get_pages', return_value=[]), patch.object(
                main_window.registry, 'get_browser_extensions', return_value=extensions), patch.object(Path, 'home', return_value=self.root):
            window = main_window.MainWindow()
        window.dlg.show()
        self.addCleanup(window.dlg.deleteLater)
        return window

    def wait_browser(self, page):
        import time
        deadline = time.monotonic() + 5
        while page.file_browser.folder_busy or page.file_browser.busy:
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents(); time.sleep(.005)
        self.app.processEvents()

    def test_browser_is_default_home_and_survives_tab_switches(self):
        from pathlib import Path
        window = self.browser_window()
        browser = window.tabs.widget(0)
        self.wait_browser(browser)
        self.assertEqual(window.tabs.tabText(0), 'File Browser')
        self.assertEqual(window.tabs.tabText(1), 'Folder Hub')
        self.assertEqual(window.tabs.currentIndex(), 0)
        self.assertEqual(browser.file_browser.navigation.library, Path(self.root.anchor))
        self.assertEqual(browser.file_browser.navigation.directory, self.root)
        (self.root / 'outside').mkdir()
        browser.workspace.active_view._open_location(self.root / 'outside')
        self.wait_browser(browser)
        self.assertEqual(browser.file_browser.navigation.library, Path(self.root.anchor))
        self.assertEqual(browser.file_browser.navigation.directory, self.root / 'outside')
        window.tabs.setCurrentIndex(1)
        window.tabs.setCurrentIndex(0)
        self.assertIs(window.tabs.widget(0), browser)
        browser.workspace.active_view._open_location(self.root)
        self.wait_browser(browser)
        self.assertEqual(browser.file_browser.navigation.library, Path(self.root.anchor))
        self.assertEqual(browser.file_browser.navigation.directory, self.root)
        window.dlg.close(); self.app.processEvents()

    def test_folder_hub_browse_uses_browser_and_preserves_scoped_views(self):
        window = self.browser_window()
        page = window.tabs.widget(0)
        self.wait_browser(page)
        folder = self.root / 'library'
        folder.mkdir()
        window.tabs.setCurrentIndex(1)
        window._browse_folder(folder)
        self.wait_browser(page)
        self.assertIs(window.tabs.currentWidget(), page)
        self.assertEqual(page.file_browser.navigation.directory, folder)
        scoped = page.workspace.add_view(folder)
        self.wait_browser(page)
        window._browse_folder(self.root)
        self.wait_browser(page)
        self.assertIsNot(page.workspace.active_view, scoped)
        self.assertEqual(scoped.file_browser.navigation.directory, folder)
        self.assertEqual(page.file_browser.navigation.directory, self.root)
        window.dlg.close(); self.app.processEvents()

    def test_document_popup_lists_and_selects_individual_text_buffers(self):
        from features.text_editor.window import EditorWindow
        from ui_new.documents import show_document
        window = self.browser_window(); self.wait_browser(window.tabs.widget(0))
        editor = EditorWindow(history_path=self.root/'recent.json', preferences_path=self.root/'editor.ini')
        first = editor.current
        editor.new_document()
        show_document(editor); self.app.processEvents()
        window.sidebar.show_documents()
        self.assertEqual(sum(item.childCount() for item in window.sidebar.editor_groups.values()), 2)
        item = window.sidebar.editor_groups['text'].child(0)
        window.sidebar.document_tree.itemClicked.emit(item, 0); self.app.processEvents()
        self.assertIs(editor.current, first)
        self.assertIs(window.tabs.currentWidget(), window.documents)
        # new_document creates another editor window sharing the session lock.
        editor.service.close_all()
        from time import monotonic, sleep
        deadline = monotonic() + 5
        while editor.service.windows:
            self.assertLess(monotonic(), deadline)
            self.app.processEvents()
            self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
            sleep(.005)
        window.dlg.close(); self.app.processEvents()

    def test_all_detached_documents_keep_documents_selected_and_sidebar_return_route(self):
        from ui_new.documents import show_document
        window = self.browser_window()
        browser = window.tabs.widget(0); self.wait_browser(browser)
        reader = qt.QMainWindow(); reader.setWindowTitle('Reader')
        show_document(reader); self.app.processEvents()
        window.documents.detach_current(); self.app.processEvents()
        self.assertGreaterEqual(window.tabs.indexOf(window.documents), 0)
        self.assertIs(window.tabs.currentWidget(), window.documents)
        self.assertTrue(window.documents.workspace.empty_new_button.isVisible())
        self.assertTrue(window.sidebar.buttons['documents'].isVisible())
        window.sidebar.show_documents()
        self.assertEqual(sum(item.childCount() for item in window.sidebar.editor_groups.values()), 1)
        row = window.sidebar.document_tree.itemWidget(window.sidebar.editor_groups['other'].child(0), 0)
        next(button for button in row.findChildren(qt.QToolButton) if button.text() == 'Bring back').click()
        self.app.processEvents()
        self.assertIs(window.tabs.currentWidget(), window.documents)
        self.assertFalse(reader.isWindow())
        window.documents.detach_current(); self.app.processEvents()
        dock = window.documents.records[reader]['dock']
        point = window.dlg.mapToGlobal(window.dlg.rect().center())
        move = qt.QMouseEvent(qt.QEvent.Type.MouseMove,
                             qt.QPointF(dock.tab_header.mapFromGlobal(point)), qt.QPointF(point),
                             qt.Qt.MouseButton.NoButton, qt.Qt.MouseButton.LeftButton,
                             qt.Qt.KeyboardModifier.NoModifier)
        self.app.sendEvent(dock.tab_header, move)
        self.assertIs(window.tabs.currentWidget(), window.documents)
        self.assertTrue(dock.is_detached)
        dock.return_button.click()
        for _ in range(5): self.app.processEvents()
        self.assertIs(window.tabs.currentWidget(), window.documents)
        self.assertFalse(dock.isFloating())
        window.dlg.close(); self.app.processEvents()

    def test_main_close_waits_for_embedded_extension_then_retries(self):
        from features.contributions import BrowserExtensionContribution
        class BusyExtension(qt.QObject):
            idle = qt.Signal()
            ready = False
            def prepare_close(self):
                return self.ready
        controller = None
        def install(host):
            nonlocal controller
            controller = BusyExtension(host)
            return controller
        extension = RegisteredContribution('test', 'Test', BrowserExtensionContribution(install))
        window = self.browser_window([extension])
        browser = window.tabs.widget(0)
        self.wait_browser(browser)
        window.dlg.close()
        self.assertTrue(window.dlg.isVisible())
        self.assertTrue(browser.closing)
        controller.ready = True
        controller.idle.emit()
        self.app.processEvents()
        self.assertFalse(window.dlg.isVisible())

    def test_main_browser_sizes_start_automatically_and_can_be_paused(self):
        with patch('commonUtils.directory_index.directory_cache.reconcile_folder',
                   return_value=Mock(folder_stats=lambda **kwargs: {})) as scan:
            window = self.browser_window()
            browser = window.tabs.widget(0)
            self.wait_browser(browser)
            self.assertTrue(browser.folder_sizes.isChecked())
            self.assertTrue(browser.folder_sizes.isHidden())
            self.assertTrue(scan.called)
            browser.folder_sizes.setChecked(False)
            self.assertFalse(browser.file_browser.calculate_folder_sizes)
            window.dlg.close(); self.app.processEvents()

    def test_browser_passes_session_policy_and_refreshes_deeper_contents(self):
        with patch('commonUtils.directory_index.directory_cache.reconcile_folder',
                   return_value=Mock(folder_stats=lambda **kwargs: {})) as scan:
            window = self.browser_window()
            page = window.tabs.widget(0)
            self.wait_browser(page)
            self.assertTrue(scan.call_args.kwargs['once'])
            page.file_browser.refresh()
            self.wait_browser(page)
            self.assertTrue(scan.call_args.kwargs['full'])
            window.dlg.close(); self.app.processEvents()
