"""Credential retries keep the original prompt and never publish failed keys."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from unittest.mock import patch
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from desktop.dialogs.archive_password import ValidatedPasswordDialog
from features.rclone.localcrypt.ui.views import ensure_session, open_browser


class CredentialUnlockTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def test_wrong_password_clears_and_focuses_same_prompt_then_accepts_retry(self):
        from PySide6.QtTest import QTest
        attempts = []
        def validate(password):
            attempts.append(password)
            if password != 'correct':
                raise ValueError('Sensitive internal error must not be displayed')
            return {'Fixture': {'type': 'local'}}
        dialog = ValidatedPasswordDialog(Path('Fixture.zip'), 'Unlock this credential ZIP.', validate)
        self.addCleanup(dialog.deleteLater)
        dialog.show()
        dialog.activateWindow()
        dialog.password.setText('wrong')
        QTest.keyClick(dialog.password, qt.Qt.Key.Key_Return)
        self.wait_until(lambda: not dialog.operation.busy)
        self.assertTrue(dialog.isVisible())
        self.assertEqual(dialog.password.text(), '')
        self.assertTrue(dialog.password.isEnabled())
        self.assertTrue(dialog.password.hasFocus())
        self.assertIn('Incorrect password', dialog.error.text())
        self.assertNotIn('Sensitive', dialog.error.text())
        self.assertIsNone(dialog.result_value)
        dialog.password.setText('correct')
        QTest.keyClick(dialog.password, qt.Qt.Key.Key_Enter)
        self.wait_until(lambda: not dialog.operation.busy)
        self.assertEqual(attempts, ['wrong', 'correct'])
        self.assertEqual(dialog.result(), qt.QDialog.DialogCode.Accepted)
        self.assertEqual(dialog.result_value, {'Fixture': {'type': 'local'}})

    def test_cancelled_unlock_does_not_create_a_browser_or_replace_credentials(self):
        from types import SimpleNamespace
        item = SimpleNamespace(context=Path('/fixture/Fixture.session'), package=Path('/fixture/Fixture.zip'))
        with patch('features.rclone.localcrypt.ui.views.executable.ensure_rclone', return_value=Path('/fixture/rclone')), \
             patch('features.rclone.localcrypt.ui.views.ensure_session', return_value=False), \
             patch('features.rclone.localcrypt.ui.views.CryptBrowserView') as window:
            self.assertIsNone(open_browser(item))
            window.assert_not_called()
        with patch('features.rclone.session.credentials', return_value=None), \
             patch('desktop.dialogs.archive_password.ask_validated_password', return_value=None), \
             patch('features.rclone.session.remember') as remember:
            self.assertFalse(ensure_session(item.context, package=item.package))
            remember.assert_not_called()
