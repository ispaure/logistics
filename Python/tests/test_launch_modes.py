"""Launch selection, sidebar-free settings, and feature retirement."""

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import Mock, patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.contributions import DocumentLauncherContribution, PageContribution, RegisteredContribution
from ui_new import main_window


class Browser(qt.QWidget):
    pass


class Settings(qt.QWidget):
    pass


class LaunchModeTests(QtTestCase):
    def setUp(self):
        super().setUp()
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.entries = [RegisteredContribution(name, name.title(), PageContribution(
            name.title(), f'{name}.workspace', qt.QWidget, order=15)) for name in ('git', 'ide')]
        self.open_comic = Mock()
        self.new_text = Mock()
        self.launchers = [RegisteredContribution('comics', 'Comics', DocumentLauncherContribution(
            'comic', 'Comic Reader', self.open_comic, 'comic', 40)),
            RegisteredContribution('text_editor', 'Text Editor', DocumentLauncherContribution(
                'text', 'Text Editor', Mock(), 'text', 10, self.new_text))]
        patcher = patch.object(main_window.registry, 'get_document_launchers', return_value=self.launchers)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name, value in (
                ('CORE_TABS', ((0, 'File Browser', Browser), (90, 'Settings', Settings))),
                ('FileBrowserPage', Browser), ('SettingsPage', Settings)):
            patcher = patch.object(main_window, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        with patch.object(main_window.registry, 'get_pages', return_value=self.entries):
            self.window = main_window.MainWindow()
        self.window.dlg.show()
        self.app.processEvents()

    def test_git_file_handoff_reveals_ide_and_respects_disabled_destination(self):
        window = self.window
        ide = window._launch_targets()['ide']
        git = window._launch_targets()['git']
        ide.open_registered_file = Mock(return_value=False)
        window._launch('git')
        self.assertFalse(git.working_file_opener('/project/file.py'))
        self.assertIs(window.tabs.currentWidget(), git)
        ide.open_registered_file.return_value = True
        self.assertTrue(git.working_file_opener('/project/file.py'))
        self.assertIs(window.tabs.currentWidget(), ide)
        self.assertEqual(window._launch_mode, 'ide')
        window._launch('hub')
        self.assertTrue(git.working_file_opener('/project/file.py'))
        self.assertEqual(window._launch_mode, 'hub')
        self.assertIs(window.tabs.currentWidget(), ide)
        window.tabs.removeTab(window.tabs.indexOf(ide))
        ide.open_registered_file.reset_mock()
        self.assertFalse(git.working_file_opener('/project/file.py'))
        ide.open_registered_file.assert_not_called()

    def test_landing_choices_reuse_pages_and_full_hub_restores_sidebar(self):
        window = self.window
        self.assertIs(window.launch_stack.currentWidget(), window.landing)
        self.assertTrue(window.sidebar.isHidden())
        self.assertEqual(window.dlg.windowTitle(), 'Logistics')
        for mode, page in window._launch_targets().items():
            window.landing.buttons[mode].click()
            self.app.processEvents()
            self.assertIs(window.tabs.currentWidget(), page)
            self.assertIs(window.launch_stack.currentWidget(), window.hub)
            self.assertTrue(window.sidebar.isHidden())
            self.assertTrue(window.settings_button.isVisible())
            window._show_landing()
        window.landing.buttons['hub'].click()
        self.assertTrue(window.sidebar.isVisible())
        self.assertTrue(window.settings_button.isHidden())
        self.assertIs(window.tabs.currentWidget(), window._launch_targets()['browser'])

    def test_settings_remains_above_content_and_returns_to_original_tool(self):
        window = self.window
        window._launch('git')
        git = window.tabs.currentWidget()
        window.show_settings_action.trigger()
        self.app.processEvents()
        self.assertIsInstance(window.tabs.currentWidget(), Settings)
        self.assertTrue(window.sidebar.isHidden())
        window.dlg.resize(900, 600)
        self.app.processEvents()
        button = window.settings_button
        surface = window.launch_surface
        self.assertEqual(button.x(), 12)
        self.assertEqual(surface.height() - button.geometry().bottom() - 1, 12)
        self.assertIs(surface.childAt(button.geometry().center()), button)
        window.return_to_tool_action.trigger()
        self.assertIs(window.tabs.currentWidget(), git)
        window._show_documents()
        self.assertTrue(button.isVisible())
        window.return_to_tool_action.trigger()
        self.assertIs(window.tabs.currentWidget(), git)

    def test_disabled_tool_returns_to_chooser_and_can_be_enabled_again(self):
        window = self.window
        window._launch('ide')
        ide = window.tabs.currentWidget()
        with patch.object(main_window.registry, 'get_pages', return_value=[]):
            window._sync_feature_pages()
        self.assertIs(window.launch_stack.currentWidget(), window.landing)
        self.assertFalse(window.landing.buttons['ide'].isEnabled())
        self.assertFalse(window.landing.buttons['git'].isEnabled())
        window._launch('ide')
        self.assertIs(window.launch_stack.currentWidget(), window.landing)
        window.show_settings_action.trigger()
        self.assertIsInstance(window.tabs.currentWidget(), Settings)
        window._show_landing()
        window.show_settings_action.trigger()
        self.assertEqual(window.dlg.windowTitle(), 'Logistics: Settings')
        with patch.object(main_window.registry, 'get_pages', return_value=self.entries):
            window._sync_feature_pages()
        window._show_landing()
        window.landing.buttons['ide'].click()
        self.assertIs(window.tabs.currentWidget(), ide)

    def test_icon_click_opens_choices_without_switching_to_settings(self):
        from PySide6.QtTest import QTest
        window = self.window
        window._launch('git')
        page = window.tabs.currentWidget()
        button = window.settings_button
        self.assertEqual(button.size(), qt.QSize(36, 36))
        self.assertEqual(button.toolButtonStyle(), qt.Qt.ToolButtonStyle.ToolButtonIconOnly)
        menu = button.menu()
        observed = []
        def inspect_menu():
            observed.append(menu.isVisible())
            menu.close()
        qt.QTimer.singleShot(0, menu, inspect_menu)
        QTest.mouseClick(button, qt.Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertEqual(observed, [True])
        self.assertIs(window.tabs.currentWidget(), page)
        self.assertEqual(menu.actions()[0].text(), 'Settings')

    def test_document_choices_use_registered_callbacks_and_preserve_cancel(self):
        window = self.window
        landing = window.landing
        self.assertIn('comic', landing.editor_buttons)
        self.assertNotIn('comic', landing.editor_new_buttons)
        self.assertIn('text', landing.editor_new_buttons)
        landing.editor_buttons['comic'].click()
        self.open_comic.assert_called_once_with(window.documents)
        self.assertIs(window.launch_stack.currentWidget(), landing)
        from commonUtils.ui.document_host import show_document
        document = qt.QMainWindow()
        document.setCentralWidget(qt.QLabel('New document'))
        self.new_text.side_effect = lambda parent: show_document(document)
        landing.editor_new_buttons['text'].click()
        self.new_text.assert_called_once_with(window.documents)
        self.assertIs(window.launch_stack.currentWidget(), window.hub)
        self.assertIs(window.tabs.currentWidget(), window.documents)
        self.assertTrue(window.sidebar.isHidden())
        self.assertTrue(window.settings_button.isVisible())
        window.show_settings_action.trigger()
        window.return_to_tool_action.trigger()
        self.assertIs(window.tabs.currentWidget(), window.documents)
        document.close()

    def test_document_choices_refresh_when_feature_is_disabled(self):
        window = self.window
        with patch.object(main_window.registry, 'get_document_launchers', return_value=[]):
            window._refresh_sidebar()
        self.assertNotIn('comic', window.landing.editor_buttons)
        self.assertIn('markdown', window.landing.editor_buttons)
        window._launch_document('comic')
        self.open_comic.assert_not_called()

    def test_settings_navigation_is_shared_and_omits_current_destination(self):
        window = self.window
        self.assertIs(window.sidebar.buttons['settings'].menu(), window.settings_button.menu())
        window._update_navigation_menu()
        self.assertFalse(window.choose_launch_mode_action.isVisible())
        window._launch('hub'); window._update_navigation_menu()
        self.assertFalse(window.open_hub_action.isVisible())
        self.assertTrue(window.choose_launch_mode_action.isVisible())
        window._show_settings(); window._update_navigation_menu()
        self.assertFalse(window.show_settings_action.isVisible())
        self.assertTrue(window.open_documents_action.isVisible())
        window._show_documents(); window._update_navigation_menu()
        self.assertFalse(window.open_documents_action.isVisible())
        window._launch('ide'); window._update_navigation_menu()
        self.assertTrue(window.open_hub_action.isVisible())
        self.assertFalse(window.return_to_tool_action.isVisible())
        window.header_menus.update_destinations()
        self.assertNotIn('Ide', [a.text() for a in window.header_menus.destinations.actions()])
