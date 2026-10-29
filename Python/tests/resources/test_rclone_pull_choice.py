"""Initial Pull choices preserve credential policy and route only after selection."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from unittest.mock import patch
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.rclone import actions
from features.rclone.transfers.ui.pull_dialog import pull_new_copy
from features.rclone.ui_contributions import _get_actions
from models.folder_entry import FolderEntry


class PullChoiceTests(QtTestCase):
    def test_only_session_crypt_without_copy_opens_choice(self):
        for suffix, crypt, chooser in [('.session', True, True), ('.conf', True, False),
                                       ('.session', False, False), ('.conf', False, False)]:
            with self.subTest(suffix=suffix, crypt=crypt):
                context = Path('/fixture/accounts' + suffix)
                entry = FolderEntry('Secret', remote_name='Secret', remote_source='rclone', remote_context=context)
                with patch('features.rclone.session.credentials', return_value={'Secret': {'type': 'crypt' if crypt else 'drive'}}), \
                     patch('features.rclone.transfers.ui.pull_dialog.pull_new_copy') as choice, \
                     patch.object(actions, 'pull_remote') as local:
                    offered = _get_actions(entry)
                    self.assertEqual([action.name for action in offered], ['Pull'])
                    self.assertFalse(offered[0].destructive)  # The retained transfer review is the approval step.
                    offered[0].callback()
                    if chooser:
                        choice.assert_called_once_with('Secret', context)
                        local.assert_not_called()
                    else:
                        local.assert_called_once_with('Secret', context, review=True)
                        choice.assert_not_called()

    def test_popup_default_and_each_choice_including_cancel(self):
        for label in ('LocalCrypt (recommended)', 'Regular Local copy', 'Cancel'):
            with self.subTest(label=label), patch.object(actions, 'pull_remote', return_value=True) as local, \
                 patch.object(actions, 'pull_encrypted_copy', return_value=True) as encrypted:
                def click():
                    dialog = qt.QApplication.activeModalWidget()
                    self.assertEqual(dialog.defaultButton().text(), 'LocalCrypt (recommended)')
                    self.assertIn('remain readable', dialog.informativeText())
                    if label == 'Cancel':
                        dialog.button(qt.QMessageBox.StandardButton.Cancel).click()
                    else:
                        next(button for button in dialog.buttons() if button.text() == label).click()
                qt.QTimer.singleShot(0, click)
                result = pull_new_copy('Secret', Path('/fixture/accounts.session'))
                self.assertEqual(result, label != 'Cancel')
                if label.startswith('LocalCrypt'):
                    encrypted.assert_called_once_with('Secret', Path('/fixture/accounts.session'), review=True)
                    local.assert_not_called()
                elif label.startswith('Regular'):
                    local.assert_called_once_with('Secret', Path('/fixture/accounts.session'), review=True)
                    encrypted.assert_not_called()
                else:
                    local.assert_not_called()
                    encrypted.assert_not_called()
