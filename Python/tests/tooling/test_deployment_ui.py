"""Exercise real asynchronous process output and the GUI upload decision."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QMessageBox
from commonUtils.tests.qt_test_case import QtTestCase
from mobile_build.deployment import deploy_ui as ui


class DeploymentUITests(QtTestCase):
    def test_settings_use_shared_navigation_and_explain_every_field(self):
        from commonUtils.ui.settings.navigation import SettingsNavigation
        from build_manager.ui import SettingsDialog
        from PySide6.QtWidgets import QSpinBox, QPlainTextEdit
        with patch.object(ui.QTimer, 'singleShot'):
            window = ui.DeploymentWindow()
        self.addCleanup(window.deleteLater)
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
        with patch.object(ui.QTimer, 'singleShot'):
            window = ui.DeploymentWindow()
        target = dict(platform='Android', id='s8', name='Galaxy S8+', online=True)
        window.update_targets([target])
        self.assertIsNone(window.target.currentData())
        window.target.setCurrentIndex(1)
        window.update_targets([])
        self.assertEqual(window.target.currentData(), dict(platform='Android', id='s8'))
        self.assertIn('unavailable', window.target.currentText())
        window.update_targets([target])
        self.assertEqual(window.target.currentText(), 'Android · Galaxy S8+')
        for script, arguments, expected in [
            ('test_devices.py', [], ['--platform', 'Android', '--device', 's8']),
            ('test_devices.py', ['--list'], ['--list']),
            ('firebase_deploy.py', ['--gui'], ['--gui']),
            ('testflight_deploy.py', ['--gui'], ['--gui']),
        ]:
            with patch.object(window.process, 'start') as start:
                window.start(script, arguments)
                self.assertEqual(start.call_args.args[1][3:], expected)
                self.assertFalse(window.target.isEnabled())
                window.set_busy(False)
        window.close()

    def test_process_reads_split_confirmation_and_only_sends_users_answer(self):
        for answer, expected in [(QMessageBox.StandardButton.Yes, 'y'), (QMessageBox.StandardButton.No, 'n')]:
            with self.subTest(expected=expected), self.temporary_directory() as directory:
                root = Path(directory) / 'mobile_build'
                (root / 'deployment').mkdir(parents=True)
                (root / '__init__.py').touch()
                (root / 'deployment/__init__.py').touch()
                (root / 'deployment/fake.py').write_text(
                    'import sys, time\n'
                    'print("Verified build", flush=True)\n'
                    f'sys.stdout.write({ui.MARKER[:10]!r}); sys.stdout.flush()\n'
                    'time.sleep(0.03)\n'
                    f'print({(ui.MARKER[10:] + json.dumps("Upload prepared build?"))!r}, flush=True)\n'
                    'print("answer=" + input(), flush=True)\n')
                with patch.object(ui.QTimer, 'singleShot'), patch.object(ui, 'ROOT', root):
                    window = ui.DeploymentWindow()
                with patch.object(ui, 'ROOT', root), patch.object(ui, 'PYTHON', Path(sys.executable)), \
                        patch.object(ui.QMessageBox, 'question', return_value=answer) as question:
                    window.start('fake.py', [])
                    self.wait_until(lambda: not window.busy, timeout=10,
                                    message='Deployment confirmation subprocess did not finish')
                    self.assertFalse(window.busy)
                    question.assert_called_once()
                    self.assertIn('answer=' + expected, window.output.toPlainText())
                    self.assertNotIn(ui.MARKER, window.output.toPlainText())
                    self.assertTrue(all(button.isEnabled() for button in window.actions))
                window.close()


if __name__ == '__main__':
    unittest.main()
