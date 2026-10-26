"""Logistics deployment policy composes the manager's generic command controls."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QMessageBox
from shiboken6 import isValid
from commonUtils.tests.qt_test_case import QtTestCase
from build_manager.deployment_commands import Command
from mobile_build.deployment import deploy_ui as ui


class DeploymentUITests(QtTestCase):
    def window(self):
        with patch.object(ui.QTimer, 'singleShot'):
            window = ui.DeploymentWindow()
        self.addCleanup(lambda: window.deleteLater() if isValid(window) else None)
        return window

    def test_settings_use_shared_navigation_and_explain_every_field(self):
        from commonUtils.ui.settings.navigation import SettingsNavigation
        from build_manager.ui import SettingsDialog
        from PySide6.QtWidgets import QSpinBox, QPlainTextEdit
        window = self.window()
        dialog = SettingsDialog(window.manager.project, window)
        self.addCleanup(dialog.deleteLater)
        self.wait_until(lambda: not dialog.busy, message='Deployment settings did not load')
        self.assertIsInstance(dialog.navigation, SettingsNavigation)
        self.assertGreater(dialog.sidebar.topLevelItemCount(), 5)
        self.assertTrue(all(field.toolTip() for field in dialog.controls.values()))
        self.assertIsInstance(dialog.controls['testflight.poll_interval_seconds'], QSpinBox)
        self.assertEqual(dialog.controls['testflight.poll_interval_seconds'].maximum(), 60)
        self.assertIsInstance(dialog.controls['testflight.what_to_test'], QPlainTextEdit)
        self.assertTrue(window.manager.cleanup.isEnabled())
        self.assertEqual(window.manager.build_override.value(), 0)
        self.assertEqual(window.manager.build_override.text(), 'Automatic')

    def test_selection_survives_refresh_and_only_routes_local_deployment(self):
        window = self.window()
        panel = window.deployment
        target = dict(platform='Android', id='s8', name='Galaxy S8+', online=True)
        panel.update_targets(panel.policy.inventory(json.dumps(dict(devices=[target], errors=[]))).targets)
        self.assertIsNone(panel.target.currentData())
        panel.target.setCurrentIndex(1)
        panel.update_targets([])
        self.assertEqual(panel.target.currentData(), dict(platform='Android', id='s8'))
        self.assertIn('unavailable', panel.target.currentText())
        panel.update_targets(panel.policy.inventory(json.dumps(dict(devices=[target], errors=[]))).targets)
        self.assertEqual(panel.target.currentText(), 'Android · Galaxy S8+')
        for action, module, arguments in [
            ('devices', 'test_devices', ['--platform', 'Android', '--device', 's8']),
            ('refresh', 'test_devices', ['--list']),
            ('repair', 'test_devices', ['--list', '--repair-android']),
            ('firebase', 'firebase_deploy', ['--gui']),
            ('testflight', 'testflight_deploy', ['--gui']),
        ]:
            with self.subTest(action=action), patch.object(panel.process, 'start') as start:
                panel.start(action)
                self.assertEqual(start.call_args.args[1], ['-u', '-m', 'mobile_build.deployment.' + module, *arguments])
                self.assertFalse(panel.target.isEnabled())
                self.assertFalse(window.manager.isEnabled())
                panel.set_busy(False)
        self.assertTrue(window.manager.isEnabled())
        window.close()

    def test_real_confirmation_and_close_guard_keep_the_legacy_protocol(self):
        with self.temporary_directory() as directory:
            window = self.window()
            panel = window.deployment
            code = f'print({ui.MARKER + json.dumps("Upload prepared build?")!r},flush=True);print("answer="+input(),flush=True)'
            command = Command((sys.executable, '-u', '-c', code), directory)
            with patch.object(panel.policy, 'command', return_value=command), \
                    patch('build_manager.deployment_commands_ui.QMessageBox.question', return_value=QMessageBox.StandardButton.No) as question:
                panel.start('firebase')
                with patch.object(ui.QMessageBox, 'information') as information:
                    self.assertFalse(window.close())
                    information.assert_called_once()
                self.wait_until(lambda: not panel.busy, timeout=10,
                                message='Deployment confirmation subprocess did not finish')
            question.assert_called_once()
            self.assertEqual(question.call_args.args[1], 'Upload prepared build?')
            self.assertIn('answer=n', panel.output.toPlainText())
            self.assertNotIn(ui.MARKER, panel.output.toPlainText())
            self.assertTrue(window.manager.isEnabled())
            window.close()

    def test_manager_run_blocks_direct_commands_and_window_close(self):
        window = self.window()
        panel = window.deployment
        window.manager.busy_changed.emit(True)
        with patch.object(panel.policy, 'command') as command, patch.object(ui.QMessageBox, 'information'):
            panel.start('firebase')
            command.assert_not_called()
            self.assertFalse(window.close())
        self.assertFalse(panel.target.isEnabled())
        window.manager.busy_changed.emit(False)
        self.assertTrue(panel.target.isEnabled())
        window.close()

    def test_policy_keeps_profile_interpreter_and_toolchain_environment(self):
        from mobile_build.deployment import manager_settings
        with self.temporary_directory() as directory:
            root = Path(directory)
            profile = root / 'profile.json'; profile.touch()
            policy = ui.LogisticsDeployment(root)
            values = {'tools.mobile_python': '/selected/python', 'tools.android_sdk': '/selected/sdk',
                      'tools.java': '/selected/java', 'tools.xcode': '/selected/xcode'}
            with patch.object(manager_settings, 'profile_path', return_value=profile), \
                    patch.object(manager_settings, 'settings', return_value=(values, {})):
                command = policy.command('firebase', dict(platform='iOS', id='phone'))
            self.assertEqual(command.argv[0], '/selected/python')
            self.assertEqual(command.cwd, str(root.parent))
            self.assertEqual(command.environment['LOGISTICS_MANAGER_PROFILE'], str(profile))
            self.assertEqual(command.environment['ANDROID_HOME'], '/selected/sdk')
            self.assertEqual(command.environment['JAVA_HOME'], '/selected/java')
            self.assertEqual(command.environment['DEVELOPER_DIR'], '/selected/xcode')
            self.assertNotIn('--device', command.argv)
            self.assertEqual(policy.logs('devices'), root / '.deploy-workspaces')
            self.assertEqual(policy.logs('firebase'), root / 'logs')


if __name__ == '__main__':
    unittest.main()
