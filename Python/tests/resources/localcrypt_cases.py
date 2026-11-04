"""Ciphertext mirror, streaming readers/editors, private UI and credential lifetime."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import time
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.rclone import executable


class LocalCryptCase(QtTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = qt.QApplication.instance() or qt.QApplication([])
        cls.binary = executable.get_rclone_path()
        if not cls.binary.is_file():
            if os.environ.get('LOGISTICS_REQUIRE_LOCALCRYPT_TESTS'):
                raise RuntimeError('Required pinned rclone is missing.')
            raise unittest.SkipTest('Pinned rclone executable not installed')

    def wait(self, predicate, seconds=30):
        deadline = time.monotonic() + seconds
        while not predicate():
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents()
            time.sleep(.01)
        self.app.processEvents()
