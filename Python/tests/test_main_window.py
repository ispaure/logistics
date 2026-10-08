"""Main navigation startup and feature page lifecycle."""

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import Mock, patch
import unittest

from commonUtils.ui import pyside as qt
from features.contributions import PageContribution, RegisteredContribution
from ui_new import main_window


class MainWindowTests(unittest.TestCase):
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

    def browser_window(self, extensions=()):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from ui_new.file_browser import FileBrowserPage
        self.temporary = TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / 'file.txt').write_text('fixture')
        with patch.object(main_window, 'CORE_TABS', ((0, 'File Browser', FileBrowserPage),
                (5, 'Known Folders', self.page), (90, 'Settings', self.page))), patch.object(
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
        self.assertEqual(window.tabs.tabText(1), 'Known Folders')
        self.assertEqual(window.tabs.currentIndex(), 0)
        self.assertEqual(browser.file_browser.navigation.library, self.root)
        with patch.object(qt.QFileDialog, 'getExistingDirectory', return_value=str(self.root / 'outside')):
            (self.root / 'outside').mkdir()
            browser.open_folder_button.click()
        self.wait_browser(browser)
        self.assertEqual(browser.file_browser.navigation.library, self.root / 'outside')
        window.tabs.setCurrentIndex(1)
        window.tabs.setCurrentIndex(0)
        self.assertIs(window.tabs.widget(0), browser)
        with patch.object(Path, 'home', return_value=self.root):
            browser.home_button.click()
        self.wait_browser(browser)
        self.assertEqual(browser.file_browser.navigation.library, self.root)
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
