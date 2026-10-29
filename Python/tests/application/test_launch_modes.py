"""Launch selection, sidebar-free settings, and feature retirement."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import Mock, patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.contributions import DocumentLauncherContribution, PageContribution, RegisteredContribution
from desktop import main_window


class Browser(qt.QWidget):
    pass


class Settings(qt.QWidget):
    pass


class LaunchModeTests(QtTestCase):
    def test_feature_browser_location_opens_in_the_existing_browser_destination(self):
        from types import SimpleNamespace
        window = self.window
        browser = next(page for _, _, page in window._core_pages if isinstance(page, Browser))
        view, location = object(), object()
        browser.workspace = SimpleNamespace(add_view=Mock(return_value=view), active_view=None)
        self.assertIs(window.dlg.open_browser_location(location), view)
        browser.workspace.add_view.assert_called_once_with(location)
        self.assertIs(window.tabs.currentWidget(), browser)

    def test_launch_cards_are_stable_from_their_first_paint(self):
        window = self.window
        from desktop.landing import LandingPage
        page = LandingPage()
        page.set_tool_launchers(window._tool_launchers())
        page.set_document_launchers(window.sidebar.launchers)
        page.resize(1250, 800)
        self.addCleanup(page.deleteLater)
        cards = page._tool_cards + page._document_cards
        first = {}
        class PaintObserver(qt.QObject):
            def eventFilter(self, watched, event):
                if event.type() == qt.QEvent.Type.Paint and watched not in first:
                    first[watched] = (watched.size(), watched.font().family(), watched.font().pointSizeF())
                return False
        observer = PaintObserver(page)
        for card in cards:
            card.installEventFilter(observer)
        page.show()
        self.wait_until(lambda: bool(first))
        for _ in range(20):
            self.app.processEvents()
        for card in first:
            self.assertEqual(first[card], (card.size(), card.font().family(), card.font().pointSizeF()))

    def setUp(self):
        super().setUp()
        self.app = qt.QApplication.instance() or qt.QApplication([])
        sidebar = patch.object(main_window, 'get_setting', return_value=False)
        sidebar.start(); self.addCleanup(sidebar.stop)
        self.entries = [RegisteredContribution(name, name.title(), PageContribution(
            name.title(), f'{name}.workspace', qt.QWidget, order=15, navigation_icon=name)) for name in ('git', 'ide')]
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

    def test_lm_file_handoff_reuses_the_ide_destination(self):
        page = self.window._create_feature_page(PageContribution('LM Chat', 'lm.chat', qt.QWidget))
        self.addCleanup(page.deleteLater)
        ide = self.window._launch_targets()['ide']
        ide.open_registered_file = Mock(return_value=True)
        self.assertTrue(page.working_file_opener('/project/file.py'))
        ide.open_registered_file.assert_called_once_with('/project/file.py')
        self.assertIs(self.window.tabs.currentWidget(), ide)

    def test_landing_choices_reuse_pages_and_full_hub_restores_sidebar(self):
        window = self.window
        self.assertIn(window.header_menus.fullscreen.action, window.header_menus.menu.actions())
        self.assertIs(window.launch_stack.currentWidget(), window.landing)
        self.assertTrue(window.sidebar.isHidden())
        self.assertEqual(window.dlg.windowTitle(), 'Logistics')
        label = window.launch_surface.version_label
        self.assertTrue(label.isVisible())
        self.assertEqual(label.x() + label.width(), window.launch_surface.width() - 12)
        home = window.sidebar.home_button
        self.assertIs(home.parentWidget().layout().itemAt(0).widget(), home)
        for mode, page in window._launch_targets().items():
            window.landing.buttons[mode].click()
            self.app.processEvents()
            self.assertIs(window.tabs.currentWidget(), page)
            self.assertIs(window.launch_stack.currentWidget(), window.hub)
            self.assertTrue(window.sidebar.isHidden())
            self.assertTrue(window.settings_button.isVisible())
            self.assertFalse(label.isVisible())
            home.click()
            self.assertIs(window.launch_stack.currentWidget(), window.landing)
            self.assertIs(window.tabs.currentWidget(), page)
            self.assertTrue(label.isVisible())
        window.landing.buttons['hub'].click()
        self.assertTrue(window.sidebar.isVisible())
        self.assertTrue(window.settings_button.isHidden())
        self.assertIs(window.tabs.currentWidget(), window._launch_targets()['browser'])

    def test_update_offer_appears_only_on_landing_page(self):
        window = self.window
        window.updates = Mock(available={'commit': 'a' * 40})
        window._update_offer_visibility()
        button = window.launch_surface.update_button
        self.assertTrue(button.isVisible())
        for mode in ('hub', 'git'):
            window._launch(mode)
            self.assertFalse(button.isVisible())
            window._show_landing()
            self.assertTrue(button.isVisible())
        window._show_document_chooser()
        self.assertFalse(button.isVisible())
        window._show_landing()
        window.updates.available = None
        window._update_offer_visibility()
        self.assertFalse(button.isVisible())

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
        self.assertNotIn('ide', window.landing.buttons)
        self.assertNotIn('git', window.landing.buttons)
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

    def test_page_contribution_adds_focused_card_and_disabled_card_disappears(self):
        extra = RegisteredContribution('sample', 'Sample', PageContribution(
            'Sample Tool', 'sample.workspace', qt.QWidget, order=30,
            navigation_icon='links', launch_description='A feature-owned launch description.'))
        key = 'feature:sample:sample.workspace'
        with patch.object(main_window.registry, 'get_pages', return_value=[*self.entries, extra]):
            self.window._sync_feature_pages()
        button = self.window.landing.buttons[key]
        self.assertEqual(button.accessibleDescription(), extra.contribution.launch_description)
        self.assertIn('browser', self.window.landing.buttons)
        self.assertIn('bulk_rename', self.window.landing.buttons)
        button.click()
        self.assertEqual(self.window._launch_mode, key)
        retained = self.window.tabs.currentWidget()
        self.assertTrue(self.window.sidebar.isHidden())
        with patch.object(main_window.registry, 'get_pages', return_value=self.entries):
            self.window._sync_feature_pages()
        self.assertNotIn(key, self.window.landing.buttons)
        self.assertIs(self.window.launch_stack.currentWidget(), self.window.landing)
        self.assertIs(self.window._feature_pages['sample', 'sample.workspace'], retained)

    def test_chooser_expands_reflows_and_scrolls_with_mouse_wheel(self):
        from desktop.landing import DocumentChooser
        chooser = DocumentChooser(); self.addCleanup(chooser.deleteLater)
        launchers = {f'sample_{i}': DocumentLauncherContribution(
            f'sample_{i}', f'Editor {i}', Mock(), 'text', i,
            description='A readable description for the document type.') for i in range(12)}
        chooser.set_document_launchers(launchers)
        chooser.resize(1400, 900); chooser.show(); self.app.processEvents()
        wide = chooser.content.width()
        self.assertEqual(wide, 880)
        self.assertEqual(chooser._document_columns, 3)
        self.assertGreater(chooser._document_cards[0].width(), 240)
        chooser.resize(500, 400); self.app.processEvents()
        self.assertLess(chooser.content.width(), wide)
        self.assertEqual(chooser._document_columns, 1)
        scrollbar = chooser.scroll.verticalScrollBar()
        self.assertGreater(scrollbar.maximum(), 0)
        point = qt.QPoint(100, 100)
        event = qt.QWheelEvent(qt.QPointF(point), qt.QPointF(chooser.scroll.viewport().mapToGlobal(point)),
                              qt.QPoint(), qt.QPoint(0, -120), qt.Qt.MouseButton.NoButton,
                              qt.Qt.KeyboardModifier.NoModifier, qt.Qt.ScrollPhase.NoScrollPhase, False)
        self.app.sendEvent(chooser.scroll.viewport(), event); self.app.processEvents()
        self.assertGreater(scrollbar.value(), 0)

    def test_tool_settings_menu_contains_only_enabled_features(self):
        from features.feature_runtime import FeatureState
        states = [FeatureState('on', 'Enabled Tool', True, True, (), ()),
                  FeatureState('off', 'Disabled Tool', True, False, (), ())]
        with patch.object(main_window.registry, 'get_feature_states', return_value=states):
            self.window.header_menus.update_settings()
        self.assertEqual([action.text() for action in self.window.header_menus.feature_settings.actions()],
                         ['Enabled Tool'])

    @patch('commonUtils.ui.appearance.typography.font_dpi', new=lambda: 72)
    def test_cards_grow_uniformly_for_wrapped_large_text(self):
        from commonUtils.ui.appearance.typography import point_size
        from desktop.landing import LandingPage
        page = LandingPage()
        self.addCleanup(page.deleteLater)
        page.set_tool_launchers([('short', 'Short', 'Small detail.', 'ide'),
                                 ('long', 'Longer workspace', 'A detailed explanation that wraps over several lines.', 'git')])
        page.set_document_launchers({str(i): DocumentLauncherContribution(
            str(i), 'Text Editor', Mock(), 'text', i, Mock(),
            description='Edit documents.' if i == 0 else 'A detailed description that needs several lines of space.')
            for i in range(3)})
        page.resize(950, 650)
        page.show()
        for _ in range(5):
            self.app.processEvents()
        initial = page._document_cards[0].height()
        font = qt.QFont(page.font())
        font.setPointSizeF(point_size(24))
        for card in page._document_cards + page._tool_cards:
            for label in card.findChildren(qt.QLabel):
                label.setFont(font)
        for width in (950, 650, 420, 950):
            page.resize(width, 650)
            for _ in range(8):
                self.app.processEvents()
            for cards in (page._document_cards, page._tool_cards):
                self.assertEqual(len({card.height() for card in cards}), 1)
                for card in cards:
                    for label in card.findChildren(qt.QLabel):
                        self.assertGreaterEqual(label.height(), label.heightForWidth(label.width()),
                            (width, card.width(), card.height(), card.layout().totalHeightForWidth(card.width()),
                             label.text(), label.width(), page._layout_text_height(card.layout()), card.minimumHeight(), card.maximumHeight()))
            self.assertGreater(page._document_cards[0].height(), initial)
        enlarged = page._document_cards[0].height()
        font.setPointSizeF(point_size(11))
        for card in page._document_cards + page._tool_cards:
            for label in card.findChildren(qt.QLabel):
                label.setFont(font)
        for _ in range(8):
            self.app.processEvents()
        self.assertLess(page._document_cards[0].height(), enlarged)
