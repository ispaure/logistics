"""Application-level browser headers retain local creation and minimum-tab rules."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import tempfile
from pathlib import Path
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.workspaces.workspace import Workspace
from desktop.file_browser import BROWSER_POLICY, _new_browser_tab


class BrowserPolicyTests(QtTestCase):
    def test_docked_single_header_and_detached_local_creation(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            class View(qt.QWidget):
                def __init__(self, path):
                    super().__init__()
                    self.path = path
                    self.workspace_controls = qt.QHBoxLayout(self)
                    self.workspace_controls.addStretch()
            main = Workspace(View, dock_group=self, policy=BROWSER_POLICY,
                             keep_one_tab=True, new_view=_new_browser_tab)
            main.add_view(Path(directory))
            main.resize(800, 500)
            main.show()
            for _ in range(8):
                self.app.processEvents()
            main.header_presentation.refresh()
            self.assertGreater(main.active_dock.tab_header.height(), 0)
            self.assertFalse(main.active_dock.close())
            self.assertIsNone(main.detach_active())
            main.add_view(Path(directory))
            window = main.detach_active()
            for _ in range(8):
                self.app.processEvents()
            detached = window.workspace
            detached.header_presentation.refresh()
            self.assertEqual(detached.active_dock.tab_header.height(), 0)
            detached.active_dock.local_new_button.click()
            for _ in range(8):
                self.app.processEvents()
            self.assertEqual(len(detached.docks), 2)
            self.assertEqual(len(main.docks), 1)
            self.assertIsNotNone(detached.active_view)
            self.assertFalse(any(dock.isFloating() for dock in detached.docks))
