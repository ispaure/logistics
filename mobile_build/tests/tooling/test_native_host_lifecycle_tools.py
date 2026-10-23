"""Full-host native evidence survives failed checks; only the QA app is removed."""
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from mobile_build.validation import native_host_lifecycle_tools as driver


class NativeHostDriverTests(unittest.TestCase):
    def test_physical_android_is_rejected_before_any_command(self):
        with TemporaryDirectory() as directory, patch.object(driver.subprocess, 'run') as command:
            with self.assertRaisesRegex(ValueError, 'dedicated Android emulator'):
                driver.validate('android', 'physical', Path(directory))
        command.assert_not_called()

    def android(self, output, report, *, keyboard=b'null\n', errors=b''):
        calls = []
        def run(arguments, **kwargs):
            calls.append(arguments)
            value = b''
            if arguments[3:7] == ('shell', 'settings', 'get', 'secure'):
                value = keyboard
            elif arguments[3:5] == ('logcat', '-d'):
                value = errors
            elif arguments[3:6] == ('exec-out', 'run-as', driver.BUNDLE):
                if arguments[-1] == 'cache/' + driver.RESULT:
                    value = json.dumps(report).encode() if report else b''
                elif arguments[-1] == 'cache/native-host-lifecycle-phase.json':
                    value = b'{"name":"waiting"}'
                elif arguments[-1] == 'cache/native-host-python-stderr.log':
                    value = b'NATIVE_HOST_STDERR_CAPTURE=started\n'
            elif arguments[3:] == ('uninstall', driver.BUNDLE):
                if report:
                    self.assertEqual(json.loads((output / driver.RESULT).read_text()), report)
            return subprocess.CompletedProcess(arguments, 0, value, b'')
        return calls, run

    def test_android_failure_saves_report_restores_keyboard_and_uninstalls_only_qa(self):
        with TemporaryDirectory() as directory:
            output = Path(directory)
            calls, run = self.android(output, {'success': False, 'error': 'native failure'})
            with patch.object(driver.subprocess, 'run', side_effect=run), self.assertRaisesRegex(AssertionError, 'native failure'):
                driver.validate('android', 'emulator-5566', output, adb='test-adb')
            self.assertFalse(json.loads((output / 'host-validation.json').read_text())['accepted'])
            self.assertEqual(calls[-1], ('test-adb', '-s', 'emulator-5566', 'uninstall', driver.BUNDLE))
            self.assertEqual(calls[-2][-5:], ('shell', 'settings', 'delete', 'secure', 'show_ime_with_hard_keyboard'))

    def test_android_success_requires_four_distinct_activity_owners(self):
        report = dict(success=True, pid=7, ime=[{}] * 3, boots=4, checks=['recreated'], activity_runs=[
            dict(activity=index, run_id=str(index), retired_previous=index > 0) for index in range(4)])
        report['activity_runs'][0]['landscape_ime'] = [{}] * 3
        with TemporaryDirectory() as directory:
            output = Path(directory)
            calls, run = self.android(output, report, keyboard=b'0\n')
            with patch.object(driver.subprocess, 'run', side_effect=run):
                self.assertEqual(driver.validate('android', 'emulator-5566', output, adb='test-adb'), report)
            self.assertTrue(json.loads((output / 'host-validation.json').read_text())['accepted'])
            self.assertEqual(calls[-2][-5:], ('settings', 'put', 'secure', 'show_ime_with_hard_keyboard', '0'))
            report['activity_runs'][1]['activity'] = 0
            with patch.object(driver.subprocess, 'run', side_effect=run), self.assertRaises(AssertionError):
                driver.validate('android', 'emulator-5566', output, adb='test-adb')
            self.assertFalse(json.loads((output / 'host-validation.json').read_text())['accepted'])

    def test_native_success_does_not_hide_swallowed_python_handler_errors(self):
        report = dict(success=True, pid=7, ime=[{}] * 3, boots=4, activity_runs=[
            dict(activity=index, run_id=str(index), retired_previous=index > 0) for index in range(4)])
        report['activity_runs'][0]['landscape_ime'] = [{}] * 3
        with TemporaryDirectory() as directory:
            output = Path(directory)
            calls, run = self.android(output, report, errors=b'Error in handler: retired view')
            with patch.object(driver.subprocess, 'run', side_effect=run), self.assertRaisesRegex(AssertionError, 'callback errors'):
                driver.validate('android', 'emulator-5566', output, adb='test-adb')
            self.assertFalse(json.loads((output / 'host-validation.json').read_text())['accepted'])
            self.assertEqual((output / 'android-python-stderr.log').read_bytes(), b'Error in handler: retired view')
            self.assertEqual(calls[-1][-2:], ('uninstall', driver.BUNDLE))

    def test_android_timeout_keeps_phase_diagnostics_and_cleans_up(self):
        with TemporaryDirectory() as directory:
            output = Path(directory)
            calls, run = self.android(output, None)
            with patch.object(driver.subprocess, 'run', side_effect=run), \
                    patch.object(driver.time, 'monotonic', side_effect=[0, 0, 999]), \
                    patch.object(driver.time, 'sleep'), self.assertRaises(TimeoutError):
                driver.validate('android', 'emulator-5566', output, adb='test-adb')
            self.assertEqual(json.loads((output / 'native-host-lifecycle-phase.json').read_text()), {'name': 'waiting'})
            self.assertEqual(calls[-1][-2:], ('uninstall', driver.BUNDLE))

    def test_ios_failure_keeps_report_before_removing_qa(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / 'container/Library/Caches'
            cache.mkdir(parents=True)
            output = root / 'evidence'
            report = {'success': False, 'error': 'scene failure'}
            def run(arguments, **kwargs):
                value = b''
                if arguments[2] == 'get_app_container':
                    value = str(root / 'container').encode()
                elif arguments[2] == 'launch':
                    (cache / driver.RESULT).write_text(json.dumps(report))
                elif arguments[2] == 'uninstall':
                    self.assertEqual(arguments[-1], driver.BUNDLE)
                    self.assertEqual(json.loads((output / driver.RESULT).read_text()), report)
                return subprocess.CompletedProcess(arguments, 0, value, b'')
            with patch.object(driver.subprocess, 'run', side_effect=run), self.assertRaisesRegex(AssertionError, 'scene failure'):
                driver.validate('ios', 'dedicated-ipad', output)

    def test_ios_native_success_still_rejects_callback_errors(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / 'container/Library/Caches'
            cache.mkdir(parents=True)
            output = root / 'evidence'
            def run(arguments, **kwargs):
                value = b''
                if arguments[2] == 'get_app_container':
                    value = str(root / 'container').encode()
                elif arguments[2] == 'launch':
                    self.assertTrue(any(arg.startswith('--stderr=') for arg in arguments))
                    (cache / driver.RESULT).write_text(json.dumps(dict(success=True, ime=[{}] * 3, windows=[{}] * 3)))
                    (output / 'ios-stderr.log').write_bytes(b'Error in handler: retired scene')
                    (cache / 'native-host-python-stderr.log').write_bytes(
                        b'NATIVE_HOST_STDERR_CAPTURE=started\nError in handler: retired scene')
                return subprocess.CompletedProcess(arguments, 0, value, b'')
            with patch.object(driver.subprocess, 'run', side_effect=run), self.assertRaisesRegex(AssertionError, 'callback errors'):
                driver.validate('ios', 'dedicated-ipad', output)
            self.assertFalse(json.loads((output / 'host-validation.json').read_text())['accepted'])
