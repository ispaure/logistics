"""Shared main-window fixtures without discoverable test cases."""

from unittest.mock import Mock, patch
from commonUtils.ui import pyside as qt
from features.contributions import PageContribution, RegisteredContribution
from desktop import main_window


class MainWindowFixture:
    """Build synthetic main windows and let QtTestCase retire their workers and widgets."""

    def run(self, result=None):
        self._window_contributions = None
        self._browser_extensions = None
        real_pages = main_window.registry.get_pages
        real_extensions = main_window.registry.get_browser_extensions
        # Settings callbacks can refresh destinations during Qt cleanup. Keep
        # synthetic pages in force until every window and worker has retired.
        with patch.object(main_window.registry, 'get_pages',
                          side_effect=lambda: real_pages() if self._window_contributions is None
                          else self._window_contributions), patch.object(
                main_window.registry, 'get_browser_extensions',
                side_effect=lambda: real_extensions() if self._browser_extensions is None
                else self._browser_extensions):
            return super().run(result)

    def setUp(self):
        super().setUp()
        self.app = qt.QApplication.instance()
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
        self._window_contributions = contributions
        with patch.object(main_window, 'CORE_TABS', (
                (0, 'Folders', self.page), (100, 'Debug', self.page))), patch.object(
                main_window.registry, 'get_pages', return_value=contributions):
            window = main_window.MainWindow()
            window._launch('hub')
        return window

    def browser_window(self, extensions=()):
        from pathlib import Path
        from desktop.file_browser import FileBrowserPage
        self._window_contributions = ()
        self._browser_extensions = extensions
        self.temporary = self.temporary_directory()
        self.root = Path(self.temporary.name)
        (self.root / 'file.txt').write_text('fixture')
        with patch.object(main_window, 'CORE_TABS', ((0, 'File Browser', FileBrowserPage),
                (5, 'Workspaces', self.page), (90, 'Settings', self.page))), patch.object(
                main_window.registry, 'get_pages', return_value=[]), patch.object(
                main_window.registry, 'get_browser_extensions', return_value=extensions), patch.object(Path, 'home', return_value=self.root):
            window = main_window.MainWindow()
        window.dlg.show()
        window._launch('hub')
        return window

    def wait_browser(self, page):
        self.wait_until(lambda: not (page.file_browser.folder_busy or page.file_browser.busy),
                        timeout=15, message='Main-window browser listing or folder index did not finish')
