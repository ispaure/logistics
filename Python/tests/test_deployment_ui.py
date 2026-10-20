"""Exercise real asynchronous process output and the GUI upload decision."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
from Mobile import deploy_ui as ui


class DeploymentUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

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
                self.assertEqual(start.call_args.args[1][2:], expected)
                self.assertFalse(window.target.isEnabled())
                window.set_busy(False)
        window.close()

    def test_process_reads_split_confirmation_and_only_sends_users_answer(self):
        for answer, expected in [(QMessageBox.StandardButton.Yes, 'y'), (QMessageBox.StandardButton.No, 'n')]:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'fake.py').write_text(
                    'import sys, time\n'
                    'print("Verified build", flush=True)\n'
                    f'sys.stdout.write({ui.MARKER[:10]!r}); sys.stdout.flush()\n'
                    'time.sleep(0.03)\n'
                    f'print({(ui.MARKER[10:] + json.dumps("Upload prepared build?"))!r}, flush=True)\n'
                    'print("answer=" + input(), flush=True)\n')
                with patch.object(ui.QTimer, 'singleShot'):
                    window = ui.DeploymentWindow()
                with patch.object(ui, 'ROOT', root), patch.object(ui, 'PYTHON', Path(sys.executable)), \
                        patch.object(ui.QMessageBox, 'question', return_value=answer) as question:
                    window.start('fake.py', [])
                    for _ in range(300):
                        QTest.qWait(10)
                        if not window.busy:
                            break
                    self.assertFalse(window.busy)
                    question.assert_called_once()
                    self.assertIn('answer=' + expected, window.output.toPlainText())
                    self.assertNotIn(ui.MARKER, window.output.toPlainText())
                    self.assertTrue(all(button.isEnabled() for button in window.actions))
                window.close()


if __name__ == '__main__':
    unittest.main()
