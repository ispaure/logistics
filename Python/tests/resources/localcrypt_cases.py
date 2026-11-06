"""Ciphertext mirror, streaming readers/editors, private UI and credential lifetime."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import time
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from tests.local_crypt_fixture import require_pinned_rclone


class LocalCryptCase(QtTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = qt.QApplication.instance() or qt.QApplication([])
        cls.binary = require_pinned_rclone()

    def wait(self, predicate, seconds=30):
        deadline = time.monotonic() + seconds
        while not predicate():
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents()
            time.sleep(.01)
        self.app.processEvents()
