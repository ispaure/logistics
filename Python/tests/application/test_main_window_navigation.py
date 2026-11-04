"""Desktop navigation, feature destinations and browser integration."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import Mock, patch
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.contributions import PageContribution, RegisteredContribution
from desktop import main_window
from tests.application._main_window_fixture import MainWindowFixture


class MainWindowNavigationTests(MainWindowFixture, QtTestCase):
    def test_menus_follow_feature_workspace_and_restore_for_plain_destinations(self):
        from commonUtils.ui.workspaces.workspace import Workspace
        def create(parent):
            page = qt.QWidget(parent)
            page.workspace = Workspace(lambda unused: qt.QMainWindow(), page)
            layout = qt.QVBoxLayout(page); layout.addWidget(page.workspace)
            document = page.workspace.add_view()
            document.menuBar().addMenu('Feature tools').addAction('Run')
            return page
        contribution = RegisteredContribution('test', 'Test', PageContribution('Tools', 'tools', create, 20))
        with patch('commonUtils.ui.workspaces.workspace_menus.sys.platform', 'darwin'):
            window = self.window([contribution]); window.dlg.show()
            feature = window._feature_pages[('test', 'tools')]
            window.tabs.setCurrentWidget(feature)
            for _ in range(3): self.app.processEvents()
            self.assertEqual([a.text() for a in window.dlg.menuBar().actions()], ['Logistics', 'Feature tools'])
            window.tabs.setCurrentWidget(window._core_pages[0][2])
            for _ in range(3): self.app.processEvents()
            self.assertEqual([a.text() for a in window.dlg.menuBar().actions()], ['Logistics'])

    def test_notification_footer_releases_space_when_empty(self):
        from desktop.notifications import notify
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

    def test_browser_x_keeps_last_tab_and_closes_only_clicked_neighbor(self):
        from PySide6.QtTest import QTest
        window = self.browser_window(); page = window.tabs.widget(0)
        self.wait_browser(page)
        workspace = page.workspace
        first = workspace.active_dock
        self.assertTrue(workspace.keep_one_tab)
        self.assertFalse(first.close())
        workspace.request_new_view(); self.wait_browser(page)
        self.assertEqual(page.file_browser.navigation.directory, self.root)
        workspace.header_presentation.refresh()
        bar = next(bar for bar in workspace.findChildren(qt.QTabBar)
                   if bar.parent() is workspace and bar.count())
        index = next(i for i in range(bar.count()) if workspace._tab_dock(bar, i) is first)
        QTest.mouseClick(bar.tabButton(index, qt.QTabBar.ButtonPosition.RightSide), qt.Qt.MouseButton.LeftButton)
        for _ in range(10): self.app.processEvents()
        self.assertEqual(len(workspace.docks), 1)
        self.assertFalse(workspace.active_dock.close())
        self.assertTrue(window.dlg.isVisible())
        self.assertFalse(window._closing)

    def test_sync_job_appears_in_the_rail_and_marks_background_completion(self):
        import sys, time
        from commonUtils.ui.tasks.process_progress import open_process
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

    def test_launch_sidebar_preference_defaults_on_and_preserves_focused_option(self):
        entry = RegisteredContribution('feature', 'Feature', PageContribution(
            'Example', 'example.page', self.page, navigation_icon='blender'))
        window = self.window([entry])
        window.dlg.show()
        key = window._launch_key('feature', 'example.page')
        for enabled in (True, False):
            with patch('desktop.main_window.get_setting', return_value=enabled) as setting:
                window._launch(key)
            self.app.processEvents()
            setting.assert_called_once_with('Menus', 'launch_with_sidebar_bool', True)
            self.assertEqual(window.sidebar.isVisible(), enabled)
            self.assertEqual(window.settings_button.isVisible(), not enabled)
            self.assertIs(window.tabs.currentWidget(), window._feature_pages[('feature', 'example.page')])
        with patch('desktop.main_window.get_setting', return_value=False):
            window._launch('hub')
        self.app.processEvents()
        self.assertTrue(window.sidebar.isVisible())

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
        from services.folders import sources as folder_sources
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
                                 ['File Browser','Workspaces','Settings','Debug'])
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

    def test_browser_is_default_home_and_survives_tab_switches(self):
        from pathlib import Path
        window = self.browser_window()
        browser = window.tabs.widget(0)
        self.wait_browser(browser)
        self.assertEqual(window.tabs.tabText(0), 'File Browser')
        self.assertEqual(window.tabs.tabText(1), 'Workspaces')
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

    def test_header_keeps_navigation_and_routes_browser_commands_across_destinations(self):
        window = self.browser_window()
        page = window.tabs.widget(0)
        self.wait_browser(page)
        bar = window.dlg.menuBar()
        self.assertEqual([action.text() for action in bar.actions()], ['Logistics', 'File', 'Edit', 'View', 'Navigate', 'Index', 'Help'])
        self.assertTrue(page.workspace.active_view.menuBar().isHidden())
        menus = page.workspace.active_view.header_menus
        page.file_browser.views.select_source(page.file_browser.model.index(str(self.root / 'file.txt')))
        menus.update()
        self.assertTrue(menus.selection.isEnabled())
        menus.selection_menu()
        self.assertIn('Bulk Rename…', [action.text() for action in menus.selection.actions()])
        menus.mode_actions[1].trigger()
        self.assertEqual(page.file_browser.view_selector.currentIndex(), 1)
        menus.preview.trigger()
        menus.update()
        self.assertEqual(menus.preview.isChecked(), page.file_browser.preview_toggle.isChecked())
        menus.selection_menu()
        window.tabs.setCurrentIndex(1)
        self.app.processEvents()
        self.assertEqual([action.text() for action in bar.actions()], ['Logistics'])
        window.header_menus.update_destinations()
        window.header_menus.destinations.actions()[0].trigger()
        self.app.processEvents()
        self.assertIs(window.tabs.currentWidget(), page)
        self.assertEqual([action.text() for action in bar.actions()], ['Logistics', 'File', 'Edit', 'View', 'Navigate', 'Index', 'Help'])
        window.dlg.close(); self.app.processEvents()

    def test_hosted_rename_menus_and_presets_remain_accessible_without_sidebar(self):
        import time
        window = self.browser_window()
        self.wait_browser(window.tabs.widget(0))
        with patch('desktop.main_window.get_setting', return_value=False):
            window._launch('browser')
        renamer = window._show_bulk_rename(self.root)
        deadline = time.monotonic() + 8
        while renamer.progress.busy or renamer.preview_timer.isActive() or renamer.plan is None:
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents(); time.sleep(.005)
        self.app.processEvents()
        self.assertEqual([action.text() for action in window.dlg.menuBar().actions()],
                         ['Logistics', 'File', 'Edit', 'View', 'Rename', 'Help'])
        self.assertTrue(window.settings_button.isVisible())
        self.assertTrue(window.sidebar.buttons['rename'].isChecked())
        window.tabs.setCurrentWidget(window.tabs.widget(0))
        self.assertFalse(window.sidebar.buttons['rename'].isChecked())
        window.tabs.setCurrentWidget(renamer)
        self.assertTrue(window.sidebar.buttons['rename'].isChecked())
        preset_rect = qt.QRect(renamer.presets_button.mapTo(window.launch_surface, qt.QPoint()),
                               renamer.presets_button.size())
        self.assertFalse(preset_rect.intersects(window.settings_button.geometry()))
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
        with patch('commonUtils.filesystem.index.directory_cache.reconcile_folder',
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
        with patch('commonUtils.filesystem.index.directory_cache.reconcile_folder',
                   return_value=Mock(folder_stats=lambda **kwargs: {})) as scan:
            window = self.browser_window()
            page = window.tabs.widget(0)
            self.wait_browser(page)
            self.assertTrue(scan.call_args.kwargs['once'])
            page.file_browser.refresh()
            self.wait_browser(page)
            self.assertTrue(scan.call_args.kwargs['full'])
            window.dlg.close(); self.app.processEvents()
