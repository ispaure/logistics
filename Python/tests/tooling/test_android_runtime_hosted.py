"""Actual runtime reports survive lost stdout without relaxing acceptance gates."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from contextlib import contextmanager
import json
from pathlib import Path
import shutil
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
    def fixture(self, *, changes=None, driver_code=0, receipt_code=0, cleanup_error=False,
                driver_error=None, receipt_error=None, scratch_error=None, startup_error=None):
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
                    if scratch_error is not None:
                        raise scratch_error
                    if not (workspace / '.keep').exists():
                        shutil.rmtree(workspace)
            class Emulator:
                def __init__(_self, sdk, path, **options):
                    events.append(('execution-context', options.get('execution_context')))
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
                        if startup_error is not None:
                            raise startup_error
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
                    if driver_error is not None:
                        raise driver_error
                    return driver_code
                raise AssertionError('Unexpected command: ' + str(argv))
            def receipt(argv, **options):
                commands.append(list(argv))
                if 'run-as' in argv:
                    self.assertNotIn('cleanup', events)
                    events.append('receipt')
                    self.assertEqual(options['timeout'], 30)
                    self.assertEqual(options['max_output'], hosted.MAX_RECEIPT_BYTES)
                    if receipt_error is not None:
                        raise receipt_error
                    if receipt_code:
                        raise OSError('receipt not found')
                    return json.dumps(report).encode()
                raise AssertionError('Unexpected command: ' + str(argv))
            with patch.object(hosted, 'scratch', scratch), patch.object(hosted, 'AndroidEmulator', Emulator), \
                    patch.object(hosted, 'load', return_value={'android_api': '36', 'android_github_abi': 'x86_64', 'android_model': 'pixel_9'}), \
                    patch.object(hosted, 'command', side_effect=command), patch.object(hosted, 'run_bytes', side_effect=receipt), \
                    patch.dict('os.environ', {'ANDROID_HOME': str(root / 'sdk')}):
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

    def test_hosted_runner_explicitly_requests_sdk_github_actions_admission(self):
        # This boundary failed in the actual hosted runner when the default
        # local context was used. The fake records selection only; SDK tests
        # and an actual hosted run establish Linux/KVM qualification.
        with self.fixture() as fixture:
            self.run_fixture(*fixture[:4])
            self.assertIn(('execution-context', 'github-actions'), fixture[4])

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


    def test_driver_failure_remains_primary_when_receipt_diagnostics_and_cleanup_also_fail(self):
        primary = RuntimeError('original driver failure')
        with self.fixture(driver_error=primary, receipt_error=OSError('receipt unavailable'),
                          cleanup_error=True, scratch_error=OSError('scratch retirement failed')) as fixture:
            with patch.object(hosted, 'diagnostics', side_effect=OSError('diagnostics copy failed')):
                with self.assertRaises(RuntimeError) as raised:
                    self.run_fixture(*fixture[:4])
            self.assertIs(raised.exception, primary)
            notes = '\n'.join(primary.__notes__)
            for phase in ('Receipt collection', 'Runtime diagnostics', 'Owned emulator cleanup', 'Scratch cleanup'):
                self.assertIn(phase, notes)
            self.assertIn('receipt', fixture[4])
            self.assertIn('cleanup', fixture[4])
            self.assertFalse((fixture[3] / 'android-result.json').exists())
            self.assertTrue((fixture[3] / 'android-cleanup-incomplete.txt').exists())

    def test_nonzero_driver_exit_precedes_missing_receipt(self):
        with self.fixture(driver_code=7, receipt_code=1) as fixture:
            with self.assertRaisesRegex(RuntimeError, 'driver failed: 7') as raised:
                self.run_fixture(*fixture[:4])
            self.assertIn('Receipt collection failed', '\n'.join(raised.exception.__notes__))
            self.assertIn('cleanup', fixture[4])

    def test_cancellation_still_collects_receipt_and_preserves_cancel_after_cleanup_failure(self):
        cancelled = KeyboardInterrupt('synthetic cancellation')
        with self.fixture(driver_error=cancelled, cleanup_error=True) as fixture:
            with self.assertRaises(KeyboardInterrupt) as raised:
                self.run_fixture(*fixture[:4])
            self.assertIs(raised.exception, cancelled)
            self.assertIn('receipt', fixture[4])
            self.assertIn('cleanup', fixture[4])
            self.assertTrue((fixture[3] / 'android-receipt.json').exists())
            self.assertFalse((fixture[3] / 'android-result.json').exists())

    def test_verification_failure_remains_primary_after_device_cleanup_failure(self):
        with self.fixture(changes={'skipped': 1}, cleanup_error=True) as fixture:
            with self.assertRaises(ValueError) as raised:
                self.run_fixture(*fixture[:4])
            self.assertIn('Owned emulator cleanup failed', '\n'.join(raised.exception.__notes__))
            self.assertFalse((fixture[3] / 'android-result.json').exists())

    def test_output_limit_failure_does_not_leave_a_stale_or_unbounded_receipt(self):
        with self.fixture(receipt_error=ValueError('output limit')) as fixture:
            fixture[3].mkdir()
            receipt = fixture[3] / 'android-receipt.json'
            receipt.write_text('old successful receipt')
            with self.assertRaisesRegex(RuntimeError, 'receipt could not be retrieved'):
                self.run_fixture(*fixture[:4])
            self.assertFalse(receipt.exists())
            self.assertFalse((fixture[3] / 'android-result.json').exists())
            self.assertIn('cleanup', fixture[4])

    def test_final_diagnostic_copy_failure_does_not_replace_primary_or_lose_cleanup_marker(self):
        primary = RuntimeError('driver failed first')
        with self.fixture(driver_error=primary, cleanup_error=True) as fixture:
            with patch.object(hosted.shutil, 'copyfile', side_effect=OSError('copy failed')):
                with self.assertRaises(RuntimeError) as raised:
                    self.run_fixture(*fixture[:4])
            self.assertIs(raised.exception, primary)
            self.assertIn('Final emulator diagnostics failed', '\n'.join(primary.__notes__))
            self.assertTrue((fixture[3] / 'android-cleanup-incomplete.txt').exists())
            self.assertEqual(fixture[4][-1], 'scratch-preserved')


    def test_invalid_receipt_remains_primary_when_diagnostic_collection_fails(self):
        with self.fixture(changes={'skipped': 1}) as fixture:
            with patch.object(hosted, 'diagnostics', side_effect=OSError('diagnostics unavailable')) as collect:
                with self.assertRaises(ValueError) as raised:
                    self.run_fixture(*fixture[:4])
            collect.assert_called_once()
            self.assertIn('Runtime diagnostics failed', '\n'.join(raised.exception.__notes__))
            self.assertIn('cleanup', fixture[4])
            self.assertFalse((fixture[3] / 'android-result.json').exists())


    def test_retention_pin_is_required_before_any_device_start(self):
        with self.fixture() as fixture:
            touch = Path.touch
            def reject_pin(path, *args, **kwargs):
                if path.name == '.keep':
                    raise OSError('cannot establish retention')
                return touch(path, *args, **kwargs)
            with patch.object(Path, 'touch', reject_pin):
                with self.assertRaisesRegex(OSError, 'cannot establish retention'):
                    self.run_fixture(*fixture[:4])
            self.assertNotIn('start', fixture[4])
            self.assertEqual(fixture[4][-1], 'scratch-released')

    def test_failed_device_cleanup_does_not_depend_on_a_late_pin_write(self):
        with self.fixture(cleanup_error=True) as fixture:
            touch = Path.touch
            pins = []
            def only_initial_pin(path, *args, **kwargs):
                if path.name == '.keep':
                    pins.append(path)
                    self.assertNotIn('start', fixture[4], 'Retention was established after device startup')
                return touch(path, *args, **kwargs)
            with patch.object(Path, 'touch', only_initial_pin):
                with self.assertRaisesRegex(RuntimeError, 'cleanup failed'):
                    self.run_fixture(*fixture[:4])
            self.assertEqual(len(pins), 1)
            self.assertTrue(pins[0].exists())
            self.assertEqual(fixture[4][-1], 'scratch-preserved')

    def test_startup_failure_cannot_leave_an_old_verified_receipt_or_device_record(self):
        with self.fixture(startup_error=RuntimeError('startup failed')) as fixture:
            reports = fixture[3]
            reports.mkdir()
            stale = [reports / name for name in ('android-result.json', 'android-result.receipt.log',
                     'android-receipt.json', 'android-testbed.log', 'android-runtime-device.json')]
            for path in stale:
                path.write_text('earlier run')
            unrelated = reports / 'unrelated-owner.json'
            unrelated.write_text('preserve')
            with self.assertRaisesRegex(RuntimeError, 'startup failed'):
                self.run_fixture(*fixture[:4])
            self.assertFalse(any(path.exists() for path in stale))
            self.assertEqual(unrelated.read_text(), 'preserve')
            self.assertIn('cleanup', fixture[4])
            self.assertEqual(fixture[4][-1], 'scratch-released')


    def test_valid_receipt_is_not_published_when_live_diagnostics_fail(self):
        with self.fixture() as fixture:
            with patch.object(hosted, 'diagnostics', side_effect=OSError('diagnostics failed')):
                with self.assertRaisesRegex(OSError, 'diagnostics failed'):
                    self.run_fixture(*fixture[:4])
            self.assertTrue((fixture[3] / 'android-receipt.json').exists())
            self.assertFalse((fixture[3] / 'android-result.json').exists())
            self.assertFalse((fixture[3] / 'android-result.receipt.log').exists())
            self.assertIn('cleanup', fixture[4])

    def test_valid_receipt_is_not_published_when_owning_cleanup_fails(self):
        for phase in ('session', 'final-copy', 'scratch'):
            options = {'cleanup_error': True} if phase == 'session' else {
                'scratch_error': OSError('scratch retirement failed')} if phase == 'scratch' else {}
            with self.subTest(phase=phase), self.fixture(**options) as fixture:
                copy = hosted.shutil.copyfile
                def copy_evidence(source, destination):
                    if phase == 'final-copy' and Path(source).name == 'removed-lease.json':
                        raise OSError('final diagnostic copy failed')
                    return copy(source, destination)
                with patch.object(hosted.shutil, 'copyfile', side_effect=copy_evidence):
                    with self.assertRaises((OSError, RuntimeError)):
                        self.run_fixture(*fixture[:4])
                self.assertTrue((fixture[3] / 'android-receipt.json').exists())
                self.assertFalse((fixture[3] / 'android-result.json').exists())
                self.assertFalse((fixture[3] / 'android-result.receipt.log').exists())
                self.assertIn('cleanup', fixture[4])

    def test_accepted_receipt_is_published_only_after_scratch_retires(self):
        with self.fixture() as fixture:
            scratch = hosted.scratch
            @contextmanager
            def retire(root):
                with scratch(root) as workspace:
                    yield workspace
                self.assertFalse(workspace.exists())
                self.assertFalse((fixture[3] / 'android-result.json').exists())
                self.assertFalse((fixture[3] / 'android-result.receipt.log').exists())
            with patch.object(hosted, 'scratch', retire):
                self.assertEqual(self.run_fixture(*fixture[:4]), self.report())
            self.assertEqual(fixture[4][-1], 'scratch-released')
            self.assertTrue((fixture[3] / 'android-result.receipt.log').exists())
            self.assertEqual(json.loads((fixture[3] / 'android-result.json').read_text()), self.report())

    def test_failed_acceptance_publication_removes_both_canonical_files(self):
        with self.fixture() as fixture:
            write = Path.write_bytes
            def fail_result(path, data):
                if path == (fixture[3] / 'android-result.json').resolve():
                    write(path, data)
                    raise OSError('result publication failed')
                return write(path, data)
            with patch.object(Path, 'write_bytes', fail_result):
                with self.assertRaisesRegex(OSError, 'result publication failed'):
                    self.run_fixture(*fixture[:4])
            self.assertFalse((fixture[3] / 'android-result.json').exists())
            self.assertFalse((fixture[3] / 'android-result.receipt.log').exists())
            self.assertTrue((fixture[3] / 'android-receipt.json').exists())
            self.assertEqual(fixture[4][-1], 'scratch-released')

    def test_retry_preserves_previous_retained_workspace_pointer(self):
        with self.fixture(cleanup_error=True) as fixture:
            reports = fixture[3]
            reports.mkdir()
            incomplete = reports / 'android-cleanup-incomplete.txt'
            previous = 'Earlier retained workspace: synthetic-previous-owner\n'
            incomplete.write_text(previous)
            with self.assertRaisesRegex(RuntimeError, 'cleanup failed'):
                self.run_fixture(*fixture[:4])
            text = incomplete.read_text()
            self.assertTrue(text.startswith(previous))
            self.assertIn('retained workspace: ' + str(fixture[0] / 'scratch'), text)
