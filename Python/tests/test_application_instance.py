"""Real per-user lock exclusion, including process lifetime and crash recovery."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import time
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import patch
from commonUtils.ui import pyside as qt
from services.application_instance import instance_lock


class InstanceTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = patch('services.application_instance.temporary_directory', return_value=Path(self.temp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def child(self, path, *, crash=False):
        code = '''import os,sys
from PySide6.QtCore import QCoreApplication, QLockFile
app=QCoreApplication([])
lock=QLockFile(sys.argv[1]); lock.setStaleLockTime(0)
print(lock.tryLock(0), flush=True)
if sys.argv[2]=='crash': os._exit(0)
'''
        return subprocess.run([sys.executable, '-c', code, str(path), 'crash' if crash else 'normal'],
                              capture_output=True, text=True, check=True, timeout=10).stdout.strip()

    def test_live_owner_cannot_expire_and_another_process_is_rejected(self):
        first = instance_lock()
        self.assertTrue(first.tryLock(0))
        self.addCleanup(first.unlock)
        path = Path(self.temp.name) / 'logistics-instance.lock'
        os.utime(path, (time()-86400, time()-86400))
        self.assertEqual(self.child(path), 'False')
        first.unlock()
        self.assertEqual(self.child(path), 'True')

    def test_crashed_owner_is_recovered(self):
        path = Path(self.temp.name) / 'logistics-instance.lock'
        self.assertEqual(self.child(path, crash=True), 'True')
        self.assertTrue(path.exists())
        recovered = instance_lock()
        self.assertTrue(recovered.tryLock(0))
        recovered.unlock()
        self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main()
