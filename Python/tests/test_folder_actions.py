"""Hosted process lifetimes and unread results, using harmless local subprocesses."""
import sys
import time
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import patch
from shiboken6 import isValid
from commonUtils.ui import pyside as qt
from commonUtils.ui.process_host import register_process_host
from commonUtils.ui.process_progress import open_process
from ui_new.folder_actions import FolderActionsPage


class FolderActionTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.host = qt.QMainWindow()
        self.tabs = qt.QTabWidget()
        self.tabs.addTab(qt.QLabel('Browser'), 'Browser')
        self.page = FolderActionsPage(self.activate, self.host)
        self.tabs.addTab(self.page, 'Folder Actions')
        self.host.setCentralWidget(self.tabs)
        self.host.resize(1000, 700); self.host.show(); self.host.activateWindow()
        register_process_host(self.page)
        self.notice = patch.object(self.page, 'notify').start()
        self.addCleanup(patch.stopall)
        self.addCleanup(self.cleanup)
        self.windows = []
        self.app.processEvents()

    def activate(self):
        self.tabs.setCurrentWidget(self.page)
        self.host.activateWindow()
        self.page.acknowledge_current()

    def wait(self, condition):
        deadline = time.monotonic() + 5
        while not condition():
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents(); time.sleep(.005)
        self.app.processEvents()

    def start(self, code):
        window = open_process('Sync', sys.executable, ['-u', '-c', code],
                              context={'operation': 'Sync', 'source': '/tmp/source', 'destination': '/tmp/destination'})
        self.windows.append(window)
        self.app.processEvents()
        return window

    def cleanup(self):
        self.page.closing = True
        for window in self.windows:
            if isValid(window):
                window.runner.cancel()
                self.wait(lambda: not isValid(window) or not window.busy)
                if isValid(window): window.close()
        self.host.close(); self.host.deleteLater()
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def test_success_and_failure_remain_in_tabs_and_unseen_results_are_acknowledged(self):
        for code, label in (("import time; time.sleep(.1); print('done')", 'Complete'),
                            ('import time; time.sleep(.1); raise SystemExit(3)', 'Failed')):
            window = self.start(code)
            self.assertFalse(window.isWindow())
            self.tabs.setCurrentIndex(0)
            self.wait(lambda: window.result is not None)
            self.assertIn(label, window.windowTitle())
            self.assertEqual(self.page.unread_count, 1)
            self.activate(); self.app.processEvents()
            self.assertEqual(self.page.unread_count, 0)
        self.assertEqual(self.page.attached_count, 2)
        self.assertEqual(self.notice.call_count, 2)

    def test_closing_a_running_tab_cancels_its_process_before_retirement(self):
        window = self.start('import time; time.sleep(10)')
        self.page.close_tab(0)
        self.wait(lambda: self.page.count == 0)
        self.assertTrue(not isValid(window) or not window.busy)

    def test_unavailable_system_notifications_leave_the_job_and_badge_intact(self):
        window = self.start("import time; time.sleep(.1)")
        self.tabs.setCurrentIndex(0); self.wait(lambda: window.result is not None)
        with patch.object(qt.QSystemTrayIcon, 'isSystemTrayAvailable', return_value=False):
            FolderActionsPage.notify(self.page, 'Done', 'Details')
        self.assertIsNone(self.page.tray)
        self.assertEqual(self.page.unread_count, 1)

    def test_supported_system_notification_uses_the_actual_result_severity(self):
        with patch('ui_new.notifications.qt.QSystemTrayIcon') as tray_type:
            tray_type.isSystemTrayAvailable.return_value = True
            tray_type.supportsMessages.return_value = True
            FolderActionsPage.notify(self.page, 'Sync failed', 'See details', failed=True)
            tray_type.return_value.showMessage.assert_called_once_with('Sync failed', 'See details',
                tray_type.MessageIcon.Warning, 5000)
            tray_type.return_value.messageClicked.connect.assert_called_once()
        self.page.tray = None
