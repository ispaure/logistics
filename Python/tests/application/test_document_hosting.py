"""Desktop document docking, menus, launchers and retained sessions."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import Mock, patch
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.contributions import RegisteredContribution
from desktop import main_window
from tests.application._main_window_fixture import MainWindowFixture


class DocumentHostingTests(MainWindowFixture, QtTestCase):
    def test_document_launcher_then_plus_menu_preserves_native_tab_menus(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from PySide6.QtTest import QTest
        from features.text_editor.contributions import register
        from features.text_editor.ui.service import EditorService
        launcher = RegisteredContribution('text_editor', 'Text Editor', register().document_launchers[0])
        with TemporaryDirectory() as temporary, patch.object(main_window.registry,
                'get_document_launchers', return_value=[launcher]), patch(
                'commonUtils.ui.workspaces.workspace_menus.sys.platform', 'darwin'):
            window = self.window(); window.dlg.show(); window.dlg.activateWindow()
            root = Path(temporary)
            service = EditorService(window.documents, history_path=root/'recent.json',
                                    preferences_path=root/'editor.ini')
            window.documents._text_editor_service = service
            window.sidebar.show_documents()
            for _ in range(3): self.app.processEvents()
            QTest.mouseClick(window.sidebar.editor_new_buttons['markdown'], qt.Qt.MouseButton.LeftButton)
            for _ in range(3): self.app.processEvents()
            workspace = window.documents.workspace
            markdown = workspace.active_view.document
            QTest.mouseClick(workspace.active_dock.local_new_button, qt.Qt.MouseButton.LeftButton)
            for _ in range(3): self.app.processEvents()
            chooser = workspace.active_view.document
            self.assertTrue(chooser._document_chooser)
            chooser.centralWidget().editor_new_buttons['text'].click()
            for _ in range(5): self.app.processEvents()
            text = workspace.active_view.document
            self.assertIsNot(text, markdown)
            native = None
            if self.app.platformName() == 'cocoa':
                from cocoa_menus import CocoaMenus
                native = CocoaMenus()
                window.dlg.activateWindow(); native.foreground()
                QTest.qWait(100)
            bar = next(bar for bar in workspace.findChildren(qt.QTabBar) if bar.parent() is workspace)
            for document in (markdown, text, markdown, text):
                dock = window.documents.records[document]['dock']
                index = next(i for i in range(bar.count()) if workspace._tab_dock(bar, i) is dock)
                point = bar.mapTo(window.dlg, bar.tabRect(index).center())
                QTest.mouseClick(window.dlg.windowHandle(), qt.Qt.MouseButton.LeftButton, pos=point)
                QTest.qWait(50)
                self.assertIs(workspace.active_view.document, document)
                file_menu = next(a.menu() for a in window.dlg.menuBar().actions() if a.text().replace('&', '') == 'File')
                commands = [a.text() for a in file_menu.actions()]
                self.assertEqual('Force Open as Text…' in commands, document is text)
                if native is not None:
                    commands = native.contents()['File']
                    self.assertEqual('Force Open as Text…' in commands, document is text)
                    self.assertEqual('Tools' in native.contents(), document is text)
            for document in (markdown, text): document.close()
            for _ in range(5): self.app.processEvents()

    def test_docked_markdown_and_text_tabs_refresh_main_menu_context(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from PySide6.QtTest import QTest
        from commonUtils.ui.document_host import show_document
        from commonUtils.ui.markdown.window import MarkdownWindow
        from features.text_editor.ui.window import EditorWindow
        with TemporaryDirectory() as temporary, patch('commonUtils.ui.workspaces.workspace_menus.sys.platform', 'darwin'):
            root = Path(temporary)
            window = self.window(); window.dlg.show(); window.dlg.activateWindow()
            markdown = MarkdownWindow(None, allow_edit=True)
            text = EditorWindow(history_path=root/'recent.json', preferences_path=root/'editor.ini')
            for document in (markdown, text): show_document(document)
            for _ in range(5): self.app.processEvents()
            workspace = window.documents.workspace
            bar = next(bar for bar in workspace.findChildren(qt.QTabBar) if bar.parent() is workspace)
            with patch.object(window, '_menu_document', wraps=window._menu_document) as resolve:
                for document in (markdown, text, markdown, text):
                    dock = window.documents.records[document]['dock']
                    index = next(i for i in range(bar.count()) if workspace._tab_dock(bar, i) is dock)
                    QTest.mouseClick(bar, qt.Qt.MouseButton.LeftButton, pos=bar.tabRect(index).center())
                    for _ in range(5): self.app.processEvents()
                    self.assertIs(workspace.active_view.document, document)
                    self.assertEqual(window.dlg.menuBar().actions(),
                                     [window.header_menus.menu.menuAction(), *document.menuBar().actions()])
                    file_menu = next(a.menu() for a in window.dlg.menuBar().actions() if a.text().replace('&', '') == 'File')
                    commands = [a.text() for a in file_menu.actions()]
                    self.assertEqual('Force Open as Text…' in commands, document is text)
                self.assertGreaterEqual(resolve.call_count, 4)
            for document in (markdown, text): document.close()
            for _ in range(5): self.app.processEvents()

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
        from commonUtils.ui.workspaces.workspace_drag import NativeWindowDrag
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
        button = bar.tabButton(index, qt.QTabBar.ButtonPosition.RightSide)
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

    def test_unopened_document_workspace_has_no_visible_controls_in_other_pages(self):
        window = self.window()
        window.dlg.show()
        self.app.processEvents()
        for sidebar in (True, False):
            window.sidebar.setVisible(sidebar)
            self.app.processEvents()
            self.assertTrue(window.documents.isHidden())
            self.assertFalse(window.documents.workspace.empty_new_button.isVisible())
            self.assertTrue(window.actions.isHidden())

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

    def test_notebook_document_appears_under_its_launcher(self):
        from features import notebooks
        from features.notebooks.ui.workspace import NotebookWindow
        from commonUtils.ui.document_host import show_document
        launcher = RegisteredContribution('notebooks', 'Notebooks', notebooks.register().document_launchers[0])
        with patch.object(main_window.registry, 'get_document_launchers', return_value=[launcher]):
            window = self.window()
            window.dlg.show()
            notebook = NotebookWindow()
            panel = qt.QWidget()
            panel.busy, panel.document, panel.dispose = False, None, Mock()
            notebook.setCentralWidget(panel)
            notebook.setWindowTitle('Meeting notes')
            try:
                show_document(notebook)
                self.app.processEvents()
                window.sidebar._populate_document_tree()
                groups = window.sidebar.editor_groups
                self.assertNotIn('other', groups)
                self.assertEqual(groups['rmdoc'].child(0).text(0), 'Meeting notes')
            finally:
                notebook.close()
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
        from desktop.documents import show_document
        contribution = self.contribution('Calculator', 'calculator')
        window = self.window([contribution]); window.dlg.show(); self.app.processEvents()
        self.assertTrue(window.tabs.tabBar().isHidden())
        self.assertEqual(window.sidebar.width(), 46)
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

    def test_document_popup_lists_and_selects_individual_text_buffers(self):
        from features.text_editor.ui.window import EditorWindow
        from desktop.documents import show_document
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
        from desktop.documents import show_document
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
