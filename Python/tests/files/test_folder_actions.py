"""Hosted process lifetimes and unread results, using harmless local subprocesses."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import sys
import time
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import patch
from shiboken6 import isValid
from commonUtils.ui import pyside as qt
from commonUtils.ui.document_host import register_document_host
from commonUtils.ui.tasks.process_host import register_process_host
from commonUtils.ui.tasks.process_progress import ProcessProgressWindow, open_process
from commonUtils.ui.tasks.process_runner import ProcessResult
from desktop.folder_actions import FolderActionsPage


class FolderActionTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.host = qt.QMainWindow()
        self.tabs = qt.QTabWidget()
        self.tabs.addTab(qt.QLabel('Browser'), 'Browser')
        self.page = FolderActionsPage(self.activate, self.host)
        self.tabs.addTab(self.page, 'Workspace actions')
        self.host.setCentralWidget(self.tabs)
        self.host.resize(1000, 700); self.host.show(); self.host.activateWindow()
        register_process_host(self.page)
        register_document_host(self.page, destination='workspace-actions')
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

    def pending_window(self):
        # Exercise the real presentation and completion signal without spawning
        # another interpreter for each notification-policy permutation.
        window = ProcessProgressWindow('Sync', context={
            'operation': 'Sync', 'source': '/tmp/source', 'destination': '/tmp/destination'})
        self.windows.append(window)
        self.page.present(window)
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

    def test_review_opens_in_transfer_view_and_skip_starts_progress_without_a_dialog(self):
        from threading import Event
        from features.rclone.transfers.review import ReviewRequest
        from features.rclone.transfers.service import TransferPlan, TransferService
        from features.rclone.transfers.ui.review import confirm_review, finish_setup_for_review

        scanned = Event()
        def scanner(emit, cancelled):
            while not cancelled():
                scanned.wait(.01)
            scanned.set()
            return ''
        request = ReviewRequest('Pull', 'Fixture:', '/tmp/destination', 'account')
        transfers = TransferService()
        prepared = transfers.prepare(TransferPlan(request, scanner, lambda: True,
            lambda *_: self.start("print('transferred')")))
        observations = []
        def skip():
            pane = self.page.workspace.active_view
            if pane is not None:
                observations.append((pane.document.isWindow(), self.tabs.currentWidget() is self.page))
                pane.document.early_button.click()
            else:
                modal = self.app.activeModalWidget()
                if modal is not None:
                    modal.reject()
        setup = qt.QDialog(self.host)
        approved = []
        def from_setup():
            finish_setup_for_review(setup)
            qt.QTimer.singleShot(0, skip)
            approved.append(confirm_review(prepared))
        qt.QTimer.singleShot(0, from_setup)
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Cancel) as question:
            self.assertEqual(setup.exec(), qt.QDialog.DialogCode.Accepted)
        self.assertEqual(approved, [prepared])
        self.assertEqual(observations, [(False, True)])
        question.assert_not_called()
        self.assertTrue(scanned.is_set())
        self.assertTrue(prepared.review.scan.retired.is_set())
        process = transfers.execute(prepared)
        self.wait(lambda: process.result is not None)
        self.assertTrue(process.result.succeeded)
        self.assertEqual(self.page.count, 1)

    def test_closing_a_running_tab_cancels_its_process_before_retirement(self):
        window = self.start('import time; time.sleep(10)')
        self.page.close_tab(0)
        self.wait(lambda: self.page.count == 0)
        self.assertTrue(not isValid(window) or not window.busy)

    def test_completion_notifications_follow_job_visibility_and_window_focus(self):
        outcomes = (
            (ProcessResult('succeeded', 0, 1), 'Complete'),
            (ProcessResult('failed', 3, 1, 'Synthetic process failure'), 'Failed'),
            (ProcessResult('cancelled', None, 1), 'Cancelled'),
        )
        with patch.object(self.host, 'isActiveWindow', return_value=True) as active, \
                patch.object(self.host, 'isMinimized', return_value=False) as minimized:
            for selected, focused, reduced, expected in (
                    (True, True, False, False),
                    (False, True, False, True),
                    (True, False, False, True),
                    (True, True, True, True)):
                with self.subTest(selected=selected, focused=focused, minimized=reduced):
                    active.return_value = focused
                    minimized.return_value = reduced
                    window = self.pending_window()
                    self.tabs.setCurrentWidget(self.page if selected else self.tabs.widget(0))
                    # Reuse the pane to test outcome projection without adding
                    # processes or rebuilding the same window for each result.
                    for result, label in outcomes:
                        with self.subTest(state=result.state):
                            self.notice.reset_mock()
                            window.runner.completed.emit(result)
                            self.assertIs(window.result, result)
                            self.assertEqual(self.page.records[window]['unseen'], expected)
                            self.assertIn(label, window.windowTitle())
                            if expected:
                                self.notice.assert_called_once_with(
                                    window.windowTitle(), result.error or 'Open Workspace actions for details.',
                                    failed=result.state == 'failed',
                                    outcome='cancelled' if result.state == 'cancelled' else None)
                            else:
                                self.notice.assert_not_called()

    def test_unavailable_system_notifications_leave_the_job_and_badge_intact(self):
        window = self.pending_window()
        self.tabs.setCurrentIndex(0)
        window.runner.completed.emit(ProcessResult('succeeded', 0, 1))
        with patch.object(qt.QSystemTrayIcon, 'isSystemTrayAvailable', return_value=False):
            FolderActionsPage.notify(self.page, 'Done', 'Details')
        self.assertIsNone(self.page.tray)
        self.assertEqual(self.page.unread_count, 1)

    def test_supported_system_notification_uses_the_actual_result_severity(self):
        with patch('desktop.notifications.qt.QSystemTrayIcon') as tray_type:
            tray_type.isSystemTrayAvailable.return_value = True
            tray_type.supportsMessages.return_value = True
            FolderActionsPage.notify(self.page, 'Sync failed', 'See details', failed=True)
            tray_type.return_value.showMessage.assert_called_once_with('Sync failed', 'See details',
                tray_type.MessageIcon.Warning, 5000)
            tray_type.return_value.messageClicked.connect.assert_called_once()
        self.page.tray = None


    def test_integrated_transfer_notices_use_safe_copy_and_keep_concurrent_results(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from commonUtils.runtime.notifications import Completion
        from desktop.notifications import notification_service
        from features.rclone.transfers.ui.progress import open_transfer_progress

        center = notification_service()
        now = 0
        with TemporaryDirectory() as root, \
                patch('desktop.transfer_notifications.start_transfer_notice',
                      side_effect=lambda: Completion(30, clock=lambda: now)), \
                patch.object(center, 'native_available', return_value=False), \
                patch.object(self.app, 'applicationState', return_value=qt.Qt.ApplicationState.ApplicationActive):
            release = Path(root) / 'release'
            private = Path(root) / 'synthetic-private.txt'
            private.write_text('fixture')
            def start(exit_code, *, revoked=lambda: False, dry_run=False):
                code = ('from pathlib import Path; import sys,time\n'
                        'while not Path(sys.argv[1]).exists(): time.sleep(.005)\n'
                        'print("Synthetic error at " + sys.argv[2], file=sys.stderr)\n'
                        'raise SystemExit(int(sys.argv[3]))')
                job = open_transfer_progress([sys.executable, '-u', '-c', code, str(release), str(private), str(exit_code)],
                    source=str(private), destination=str(Path(root) / 'destination'),
                    dry_run=dry_run, credential_path=private, revoked=revoked, cancelled=lambda: False,
                    session_bound=False)
                self.windows.append(job)
                return job

            short = start(0)
            release.touch()
            self.tabs.setCurrentIndex(0)
            self.wait(lambda: not short.busy)
            self.assertFalse(any(n.source == 'transfer' for n in center.records.values()))
            release.unlink()
            normal, failed = start(0), start(1)
            dry = start(0, dry_run=True)
            cancelled = start(0)
            self.tabs.setCurrentIndex(0)
            now = 31
            cancelled.runner.cancel()
            self.wait(lambda: not cancelled.busy)
            release.touch()
            self.wait(lambda: all(not job.busy for job in (normal, failed, dry)))
            notices = [n for n in center.records.values() if n.source == 'transfer']
            self.assertEqual({n.outcome for n in notices}, {'success', 'failure'})
            self.assertEqual(len(notices), 2)
            normal.runner.completed.emit(normal.result)
            self.assertEqual(len([n for n in center.records.values() if n.source == 'transfer']), 2)
            failure = next(n for n in notices if n.outcome == 'failure')
            self.assertNotIn('synthetic-private', failure.title + failure.message)
            self.assertIn('before retrying', failure.message)
            failure.activate()
            self.assertIs(self.page.workspace.active_view.document, failed)

            # Revocation can win a terminal-signal race before the process guard polls.
            release.unlink()
            locked = False
            protected = start(1, revoked=lambda: locked)
            self.tabs.setCurrentIndex(0)
            locked = True
            now += 31
            protected.runner.completed.emit(ProcessResult('failed', 1, 1, str(private)))
            last = list(center.records.values())[-1]
            self.assertEqual(last.message, 'Unlock in Logistics to review the transfer.')
            self.assertIsNone(last.activate)
