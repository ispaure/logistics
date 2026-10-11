"""Project tree ordering through the real asynchronous filesystem model."""
import tempfile
import time
from pathlib import Path

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.ide.browser import ProjectBrowser
from features.ide.projects import Project


class ProjectBrowserTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def wait_for_names(self, browser, path, expected):
        deadline = time.monotonic() + 5
        while True:
            self.app.processEvents()
            parent = browser.proxy.mapFromSource(browser.model.index(str(path)))
            names = [browser.proxy.data(browser.proxy.index(row, 0, parent))
                     for row in range(browser.proxy.rowCount(parent))]
            if names == expected:
                return
            self.assertLess(time.monotonic(), deadline, names)
            time.sleep(.001)

    def test_folders_first_natural_names_nested_filter_and_new_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for name in ('a10.py', 'a2.py', 'B.py'):
                (root / name).touch()
            for name in ('z10', 'z2'):
                (root / name).mkdir()
            nested = root / 'z2'
            (nested / 'a.py').touch()
            (nested / 'z_folder').mkdir()
            owner = qt.QWidget()
            browser = ProjectBrowser(Project('test', str(root)), owner)
            self.wait_for_names(browser, root, ['z2', 'z10', 'a2.py', 'a10.py', 'B.py'])
            nested_index = browser.proxy.mapFromSource(browser.model.index(str(nested)))
            browser.tree.expand(nested_index)
            self.wait_for_names(browser, nested, ['z_folder', 'a.py'])
            browser.filter.setText('a')
            self.wait_for_names(browser, root, ['z2', 'z10', 'a2.py', 'a10.py'])
            browser.filter.clear()
            (root / 'z1').mkdir()
            (root / 'a1.py').touch()
            self.wait_for_names(browser, root, ['z1', 'z2', 'z10', 'a1.py', 'a2.py', 'a10.py', 'B.py'])
            browser.locate(root / 'a2.py')
            self.assertEqual(browser.path(), root / 'a2.py')
            owner.close()
