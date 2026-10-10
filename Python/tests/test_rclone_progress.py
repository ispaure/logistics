import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from features.rclone.progress import RcloneProgressParser
from features.rclone.sync import build_sync_arguments, rclone_sync
from commonUtils.ui import pyside as qt


class RcloneProgressTests(QtTestCase):
    def test_parser_reads_progress_and_builtin_attempts_without_inventing_success(self):
        parser = RcloneProgressParser()
        update = parser(json.dumps({'stats': {'bytes': 50, 'totalBytes': 100, 'speed': 10, 'transfers': 1, 'totalTransfers': 2}}))
        self.assertEqual((update.done, update.total, update.attempt), (50, 100, 1))
        failed = parser(json.dumps({'msg': 'Attempt 1/3 failed with 2 errors'}))
        self.assertEqual((failed.state, failed.attempt), ('retrying', 2))
        success = parser(json.dumps({'msg': 'Attempt 2/3 succeeded'}))
        self.assertEqual(success.attempt, 2)
        self.assertEqual(success.state, 'running')  # Only an exit code can establish final success.
        self.assertIsNone(parser(''))

    def test_streamed_retry_success_is_confirmed_by_the_actual_exit(self):
        import sys
        import time
        from commonUtils.ui.process_progress import ProcessProgressWindow
        from commonUtils.ui.process_runner import ProcessRunner
        app = qt.QApplication.instance() or qt.QApplication([])
        for code, expected in ((0, 'succeeded'), (9, 'failed')):
            window = ProcessProgressWindow('Simulated rclone', runner=ProcessRunner(parser=RcloneProgressParser()))
            window.show()
            script = ("import json; print(json.dumps({'msg':'Attempt 1/3 failed with 1 errors'})); "
                      "print(json.dumps({'msg':'Attempt 2/3 succeeded'})); "
                      f"raise SystemExit({code})")
            window.start(sys.executable, ['-u', '-c', script])
            deadline = time.monotonic() + 5
            while window.busy:
                self.assertLess(time.monotonic(), deadline)
                app.processEvents(); time.sleep(.01)
            self.assertEqual(window.result.state, expected)
            self.assertEqual(window.result.attempt, 2)
            window.close(); app.processEvents()

    def test_arguments_keep_transfer_options_and_literal_paths(self):
        arguments = build_sync_arguments('/rclone', '/source $ ` spaces-VM', 'Remote:destination',
            config_path='/config with spaces.conf', track_renames=True, bw_limit='12', dry_run=True)
        self.assertIn('--copy-links', arguments)
        self.assertIn('--track-renames', arguments)
        self.assertIn('--transfers=1', arguments)
        self.assertIn('--dry-run', arguments)
        self.assertIn('--use-json-log', arguments)
        self.assertEqual(arguments[-3:], ['--', '/source $ ` spaces-VM', 'Remote:destination'])
        self.assertNotIn('--retries', arguments)

    def test_gui_sync_uses_integrated_window_and_preserves_explicit_context(self):
        app = qt.QApplication.instance() or qt.QApplication([])
        with TemporaryDirectory() as temp:
            destination = Path(temp) / 'destination'
            with patch('features.rclone.sync.executable.ensure_rclone', return_value=Path('/rclone')), \
                    patch('commonUtils.ui.process_progress.open_process') as opened, \
                    patch('features.rclone.sync.cmdShellWrapper.exec_cmd') as console:
                self.assertTrue(rclone_sync('Remote:', destination, config_path='/selected.conf'))
                console.assert_not_called()
                self.assertEqual(Path(opened.call_args.args[1]), Path('/rclone'))
                self.assertIn('/selected.conf', opened.call_args.args[2])
                self.assertTrue(destination.is_dir())

    def test_real_local_rclone_sync_and_failure_when_executable_available(self):
        import time
        from features.rclone.executable import get_rclone_path
        from commonUtils.ui.process_progress import _windows
        executable = get_rclone_path()
        if not executable.is_file():
            self.skipTest('Pinned rclone executable not installed')
        app = qt.QApplication.instance() or qt.QApplication([])
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'source'; source.mkdir()
            (source / 'file.txt').write_text('fixture')
            config = root / 'empty.conf'; config.touch()
            def run(src, dst):
                with patch('features.rclone.sync.executable.ensure_rclone', return_value=executable):
                    self.assertTrue(rclone_sync(src, dst, config_path=config))
                window = _windows[-1]
                deadline = time.monotonic() + 10
                while window.busy:
                    self.assertLess(time.monotonic(), deadline)
                    app.processEvents(); time.sleep(.01)
                return window
            window = run(source, root / 'destination')
            self.assertTrue(window.result.succeeded)
            self.assertEqual((root / 'destination' / 'file.txt').read_text(), 'fixture')
            self.assertTrue(window.isVisible())
            window.close(); app.processEvents()
            failed = run(root / 'missing-source', root / 'other-destination')
            self.assertEqual(failed.result.state, 'failed')
            self.assertNotEqual(failed.result.exit_code, 0)
            failed.close(); app.processEvents()
