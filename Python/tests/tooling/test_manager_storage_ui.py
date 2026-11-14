"""Exercise asynchronous storage review against real owned fixture directories."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox

from commonUtils.filesystem.index import DirectoryCache

from build_manager.storage_ui import StorageDialog
from build_manager.storage_inventory import CACHES


class SettingsAndStorageUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        from PySide6.QtCore import QThreadPool, QCoreApplication, QEvent
        QThreadPool.globalInstance().waitForDone(5000)
        for widget in self.app.topLevelWidgets():
            widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def wait(self, dialog):
        deadline = time.monotonic() + 5
        while dialog.busy:
            self.app.processEvents()
            self.assertLess(time.monotonic(), deadline)
            time.sleep(.005)

    def test_filtered_select_available_reviews_owned_rows_before_deleting_and_refreshes(self):
        from logistics_build.build_retention import compiler_cache, storage_inventory, delete_storage
        with TemporaryDirectory() as directory, \
                patch('logistics_build.xcode_storage.storage_group',
                      side_effect=lambda project: dict(root=Path(project) / 'xcode-cache', eligible=lambda path: False)), \
                patch('logistics_build.storage_extras.simulator_inventory', return_value=[]):
            root = Path(directory).resolve()
            with compiler_cache('available', root) as available, compiler_cache('pinned', root) as pinned:
                (pinned / '.keep').touch()
            build = root / 'mobile_build/build/firebase/1'
            build.mkdir(parents=True)

            class Project:
                def __init__(self, root):
                    self.root = root

                def storage_inventory(self):
                    return storage_inventory(self.root)

                def delete_storage(self, selections):
                    return delete_storage(self.root, selections)

            with patch('commonUtils.filesystem.index.DirectoryCache',
                       partial(DirectoryCache, database=root / 'storage.sqlite')):
                dialog = StorageDialog(Project(root))
                self.wait(dialog)
                self.assertEqual(dialog.table.topLevelItemCount(), 3)
                dialog.group.setCurrentText(CACHES)
                self.wait(dialog)
                self.assertEqual(dialog.table.topLevelItemCount(), 2)
                dialog.all.click()
                self.assertEqual([item.toolTip(0) for item in dialog.table.selectedItems()], [str(available)])
                self.assertTrue(available.exists())
                with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.No) as confirm:
                    dialog.selected.click()
                    self.wait(dialog)
                confirm.assert_called_once()
                self.assertTrue(available.exists())
                with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Yes) as confirm, \
                        patch.object(QMessageBox, 'information'):
                    dialog.selected.click()
                    self.wait(dialog)
                confirm.assert_called_once()
                self.assertFalse(available.exists())
                self.assertTrue(pinned.exists())
                self.assertTrue(build.exists())
                self.assertEqual(dialog.table.topLevelItemCount(), 1)
                dialog.all.click()
                self.assertFalse(dialog.table.selectedItems())
                self.assertFalse(dialog.selected.isEnabled())
                dialog.close()
