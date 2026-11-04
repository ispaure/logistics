"""Actual runtime reports survive lost stdout without relaxing acceptance gates."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from contextlib import contextmanager
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from logistics_build import android_runtime_hosted as hosted
from mobile import smoke


class RuntimeReceiptWriterTests(unittest.TestCase):
    def test_completed_success_and_failure_are_atomic_before_stdout_even_when_stdout_is_lost(self):
        for success in (True, False):
            with self.subTest(success=success), TemporaryDirectory() as directory:
                path = Path(directory) / 'result.json'
                path.write_text('previous receipt')
                report = dict(success=success, failures=0 if success else 1)
                def lost_stdout(line, **kwargs):
                    self.assertEqual(json.loads(path.read_text()), report)
                    self.assertEqual(line, smoke.PREFIX + json.dumps(report, sort_keys=True))
                    raise BrokenPipeError('logcat disconnected')
                with patch('builtins.print', side_effect=lost_stdout), self.assertRaises(BrokenPipeError):
                    smoke.publish_result(report, path)
                self.assertEqual(json.loads(path.read_text()), report)
                self.assertEqual(list(path.parent.iterdir()), [path])

    def test_failed_atomic_write_preserves_previous_receipt_and_does_not_print_success(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'result.json'
            path.write_text('old')
            with patch.object(smoke.os, 'fsync', side_effect=OSError('disk failure')), patch('builtins.print') as out:
                with self.assertRaises(OSError):
                    smoke.publish_result({'success': True}, path)
            out.assert_not_called()
            self.assertEqual(path.read_text(), 'old')
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_absent_result_file_preserves_single_original_stdout_marker(self):
        report = {'success': False}
        with patch('builtins.print') as out:
            smoke.publish_result(report)
        out.assert_called_once_with(smoke.PREFIX + json.dumps(report, sort_keys=True), flush=True)


class HostedAndroidRuntimeTests(unittest.TestCase):
    def report(self):
        return dict(schema=1, suite='logistics-mobile-documents', target='android', sys_platform='android',
                    environment='android-emulator', success=True, failures=0, errors=0, skipped=0,
                    tests_run=len(smoke.EXPECTED_TESTS), expected_tests=list(smoke.EXPECTED_TESTS),
                    source=dict(dirty=False, logistics_commit='a' * 40, commonUtils_commit='b' * 40))

    @contextmanager
    def fixture(self, *, changes=None, driver_code=0, receipt_code=0, cleanup_error=False):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cpython, payload, reports, workspace = (root / name for name in ('cpython', 'payload', 'reports', 'scratch'))
            for folder in (cpython, payload, workspace):
                folder.mkdir()
            original = self.report()
            (payload / 'source.json').write_text(json.dumps(original['source']))
            report = dict(original, **(changes or {}))
            events, commands = [], []
            @contextmanager
            def scratch(_root):
                try:
                    yield workspace
                finally:
                    events.append('scratch-preserved' if (workspace / '.keep').exists() else 'scratch-released')
            class Emulator:
                def __init__(_self, sdk, path, **options):
                    _self.workspace = path
                    _self.marker = path / 'lease.json'
                    _self.adb = root / 'sdk/platform-tools/adb'
                @contextmanager
                def session(_self, image, model):
                    events.append('start')
                    _self.workspace.mkdir()
                    _self.marker.write_text('{}')
                    (_self.workspace / 'emulator.log').write_text('owned emulator diagnostics')
                    try:
                        yield {'serial': 'emulator-5554'}
                    finally:
                        events.append('cleanup')
                        if cleanup_error:
                            raise RuntimeError('owned cleanup failed')
                        _self.marker.rename(_self.workspace / 'removed-lease.json')
                def verify(_self, record):
                    events.append('verify')
                def invoke(_self, *args, **options):
                    return 'best effort logcat'
            def command(argv, cwd, timeout, **options):
                commands.append(list(argv))
                if 'Android/android.py' in argv:
                    events.append('driver')
                    self.assertIn('--connected', argv)
                    self.assertNotIn('--managed', argv)
                    self.assertEqual(argv[argv.index('--connected') + 1], 'emulator-5554')
                    options['stdout'].write('Gradle testPython PASSED; logcat lost, no JSON marker\n')
                    return driver_code
                if 'run-as' in argv:
                    self.assertNotIn('cleanup', events)
                    events.append('receipt')
                    self.assertEqual(timeout, 30)
                    options['stdout'].write('not found' if receipt_code else json.dumps(report))
                    return receipt_code
                raise AssertionError('Unexpected command: ' + str(argv))
            with patch.object(hosted, 'scratch', scratch), patch.object(hosted, 'AndroidEmulator', Emulator), \
                    patch.object(hosted, 'load', return_value={'android_api': '36', 'android_github_abi': 'x86_64', 'android_model': 'pixel_9'}), \
                    patch.object(hosted, 'command', side_effect=command), patch.dict('os.environ', {'ANDROID_HOME': str(root / 'sdk')}):
                yield root, cpython, payload, reports, events, commands

    def run_fixture(self, root, cpython, payload, reports):
        return hosted.run(root, cpython, payload, reports, install_image=False)

    def test_actual_receipt_is_verified_when_stdout_marker_is_missing_then_owned_device_is_cleaned(self):
        with self.fixture() as (root, cpython, payload, reports, events, commands):
            actual = self.run_fixture(root, cpython, payload, reports)
            self.assertEqual(actual, self.report())
            self.assertLess(events.index('receipt'), events.index('cleanup'))
            self.assertEqual(events[-1], 'scratch-released')
            self.assertTrue((reports / 'android-removed-lease.json').exists())
            self.assertTrue((reports / 'android-logcat.log').exists())
            self.assertIn('no JSON marker', (reports / 'android-testbed.log').read_text())
            app_path = commands[0][commands[0].index('--result-file') + 1]
            adb_path = commands[1][-1]
            self.assertEqual(app_path.removeprefix('../../'), adb_path.removeprefix('files/'))

    def test_failed_skipped_partial_or_foreign_receipt_never_passes(self):
        for changes in ({'success': False, 'failures': 1}, {'skipped': 1}, {'tests_run': len(smoke.EXPECTED_TESTS) - 1},
                        {'source': dict(self.report()['source'], logistics_commit='c' * 40)}):
            with self.subTest(changes=changes), self.fixture(changes=changes) as fixture:
                with self.assertRaises(ValueError):
                    self.run_fixture(*fixture[:4])
                self.assertIn('cleanup', fixture[4])
                self.assertFalse((fixture[3] / 'android-result.json').exists())

    def test_missing_receipt_or_driver_failure_never_uses_gradle_or_report_as_pass(self):
        for options in ({'receipt_code': 1}, {'driver_code': 7}):
            with self.subTest(options=options), self.fixture(**options) as fixture:
                with self.assertRaises(RuntimeError):
                    self.run_fixture(*fixture[:4])
                self.assertIn('cleanup', fixture[4])
                self.assertFalse((fixture[3] / 'android-result.json').exists())

    def test_cleanup_failure_preserves_owned_workspace_and_reports_leftover(self):
        with self.fixture(cleanup_error=True) as fixture:
            with self.assertRaisesRegex(RuntimeError, 'cleanup failed'):
                self.run_fixture(*fixture[:4])
            self.assertEqual(fixture[4][-1], 'scratch-preserved')
            self.assertTrue((fixture[3] / 'android-cleanup-incomplete.txt').exists())

    def test_receipt_path_validation_and_size_limit(self):
        with self.assertRaises(ValueError):
            hosted.receipt_paths('../not-owned')
        with TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = root / 'receipt.json'
            receipt.write_bytes(b' ' * (hosted.MAX_RECEIPT_BYTES + 1))
            with self.assertRaisesRegex(ValueError, 'bounded'):
                hosted.verify_receipt(receipt, root / 'missing-source', root / 'result.json')
