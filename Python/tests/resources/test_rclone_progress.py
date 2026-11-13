"""Check rclone progress parsing, retry completion and desktop sync command routing."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import warnings
from commonUtils.tests.qt_test_case import QtTestCase
from features.rclone.transfers.progress import RcloneProgressParser
from features.rclone.transfers.sync import build_sync_arguments, rclone_sync
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
        from commonUtils.ui.tasks.process_progress import _windows
        app = qt.QApplication.instance() or qt.QApplication([])
        for code, expected in ((0, 'succeeded'), (9, 'failed')):
            script = ("import json; print(json.dumps({'msg':'Attempt 1/3 failed with 1 errors'})); "
                      "print(json.dumps({'msg':'Attempt 2/3 succeeded'})); "
                      "print(json.dumps({'stats': {'transfers': 0, 'totalTransfers': 0, "
                      "'deletes': 1234, 'deletedDirs': 0}})); "
                      f"raise SystemExit({code})")
            with TemporaryDirectory() as destination, \
                    patch('features.rclone.transfers.sync.executable.ensure_rclone', return_value=Path(sys.executable)), \
                    patch('features.rclone.transfers.sync.build_sync_arguments',
                          return_value=[sys.executable, '-u', '-c', script]):
                self.assertTrue(rclone_sync('Remote:', destination, config_path='/selected.conf'))
            window = _windows[-1]
            deadline = time.monotonic() + 5
            while window.busy:
                self.assertLess(time.monotonic(), deadline)
                app.processEvents(); time.sleep(.01)
            self.assertEqual(window.result.state, expected)
            self.assertEqual(window.result.attempt, 2)
            self.assertEqual(window.fields['files'].text(), '0 / 0')
            self.assertEqual(window.fields['deleted'].text(), '1,234')
            self.assertEqual(window.fields['deleted_dirs'].text(), '0')
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
            with patch('features.rclone.transfers.sync.executable.ensure_rclone', return_value=Path('/rclone')), \
                    patch('commonUtils.ui.tasks.process_progress.open_process') as opened, \
                    patch('features.rclone.transfers.ui.progress.watch_transfer') as watch, \
                    patch('features.rclone.transfers.sync.cmdShellWrapper.exec_cmd') as console:
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter('always')
                    self.assertTrue(rclone_sync('Remote:', destination, config_path='/selected.conf'))
                self.assertEqual(caught, [])
                console.assert_not_called()
                watch.assert_called_once()
                self.assertEqual(Path(opened.call_args.args[1]), Path('/rclone'))
                self.assertIn('/selected.conf', opened.call_args.args[2])
                self.assertTrue(destination.is_dir())

    def test_legacy_presentation_helpers_delegate_and_warn_once_per_call_site(self):
        from features.rclone.transfers import progress, sync
        window, config_path, revoked, cancelled = object(), Path('/selected.conf'), object(), object()
        with patch('features.rclone.transfers.ui.progress.watch_transfer') as watch, \
                patch('features.rclone.transfers.ui.progress.add_removal_statistics') as statistics, \
                warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('default', FutureWarning)
            for _ in range(2):
                self.assertIs(sync._watch_transfer(window, config_path, revoked, cancelled,
                    session_bound=True), watch.return_value)
                self.assertIs(progress.add_removal_statistics(window, dry_run=True), statistics.return_value)
        self.assertEqual(watch.call_count, 2)
        watch.assert_called_with(window, config_path, revoked, cancelled, session_bound=True)
        self.assertEqual(statistics.call_count, 2)
        statistics.assert_called_with(window, dry_run=True)
        self.assertEqual(len(caught), 2)
        for warning, old, new in zip(caught, (
                'features.rclone.transfers.sync._watch_transfer',
                'features.rclone.transfers.progress.add_removal_statistics'), (
                'features.rclone.transfers.ui.progress.watch_transfer',
                'features.rclone.transfers.ui.progress.add_removal_statistics')):
            self.assertIs(warning.category, FutureWarning)
            self.assertIn(old, str(warning.message))
            self.assertIn(new, str(warning.message))
            self.assertIn('same arguments', str(warning.message))
            self.assertEqual(Path(warning.filename), Path(__file__))

    def test_real_local_rclone_sync_and_failure_when_executable_available(self):
        import time
        from features.rclone.executable import get_rclone_path
        from commonUtils.ui.tasks.process_progress import _windows
        executable = get_rclone_path()
        if not executable.is_file():
            self.skipTest('Pinned rclone executable not installed')
        app = qt.QApplication.instance() or qt.QApplication([])
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'source'; source.mkdir()
            (source / 'file.txt').write_text('fixture')
            config = root / 'empty.conf'; config.touch()
            def run(src, dst, *, dry_run=False):
                with patch('features.rclone.transfers.sync.executable.ensure_rclone', return_value=executable):
                    self.assertTrue(rclone_sync(src, dst, config_path=config, dry_run=dry_run))
                window = _windows[-1]
                deadline = time.monotonic() + 10
                while window.busy:
                    self.assertLess(time.monotonic(), deadline)
                    app.processEvents(); time.sleep(.01)
                return window
            destination = root / 'destination'
            destination.mkdir()
            extra = destination / 'extra'
            extra.mkdir()
            (extra / 'stale.txt').touch()
            preview = run(source, destination, dry_run=True)
            self.assertTrue(preview.result.succeeded)
            self.assertEqual(preview.fields['deleted'].text(), '1')
            self.assertTrue((extra / 'stale.txt').exists())
            preview.close(); app.processEvents()
            window = run(source, destination)
            self.assertTrue(window.result.succeeded)
            self.assertEqual((destination / 'file.txt').read_text(), 'fixture')
            self.assertFalse(extra.exists())
            self.assertEqual(window.fields['deleted'].text(), '1')
            self.assertEqual(window.fields['deleted_dirs'].text(), '1')
            self.assertTrue(window.isVisible())
            window.close(); app.processEvents()
            failed = run(root / 'missing-source', root / 'other-destination')
            self.assertEqual(failed.result.state, 'failed')
            self.assertNotEqual(failed.result.exit_code, 0)
            failed.close(); app.processEvents()
