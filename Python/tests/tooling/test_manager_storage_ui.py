"""Exercise asynchronous storage review against real owned fixture directories."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox, QSpinBox

from build_manager.storage_ui import StorageDialog
from build_manager.ui import SettingsDialog
from build_manager.retention import delete_owned, lease, owned_entries


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

    def test_filtered_delete_all_uses_reviewed_owned_rows_and_refreshes(self):
        from Scripts.build_retention import storage_inventory, delete_storage
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for group in ('firebase', 'testflight'):
                for build in ('1', '2'):
                    (root / 'mobile_build/build' / group / build).mkdir(parents=True)
            (root / 'mobile_build/build/firebase/2/.keep').touch()
            class Project:
                def storage_inventory(self):
                    return storage_inventory(root)
                def delete_storage(self, selections):
                    return delete_storage(root, selections)
            dialog = StorageDialog(Project())
            self.wait(dialog)
            dialog.group.setCurrentText('Android / Firebase')
            self.assertEqual(dialog.table.topLevelItemCount(), 2)
            with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.No):
                dialog.remove(True)
            self.assertTrue((root / 'mobile_build/build/firebase/1').exists())
            with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Yes), \
                    patch.object(QMessageBox, 'information'):
                dialog.remove(True)
                self.wait(dialog)
            self.assertFalse((root / 'mobile_build/build/firebase/1').exists())
            self.assertTrue((root / 'mobile_build/build/firebase/2').exists())
            self.assertTrue((root / 'mobile_build/build/testflight/1').exists())
            self.assertEqual(dialog.table.topLevelItemCount(), 1)
            self.assertFalse(dialog.all.isEnabled())
            dialog.close()
