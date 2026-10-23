"""External lifecycle checks keep evidence and scope commands to the QA app."""
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from mobile_build.validation.native_lifecycle_tools import BUNDLE, validate


class AndroidProbe:
    """Model live checkpoints while recording the driver's native commands."""

    def __init__(self, *, passed=True, partial=False, restart=False, visible=True):
        self.case = 0
        self.tick = 0
        self.size = None
        self.passed = passed
        self.partial = partial
        self.restart = restart
        self.visible = visible
        self.calls = []

    def __call__(self, arguments, **kwargs):
        self.calls.append(arguments)
        data = b''
        if arguments[3:6] == ('shell', 'wm', 'size'):
            self.size = arguments[6]
        if arguments[3:8] == ('shell', 'run-as', BUNDLE, 'sh', '-c'):
            if 'native-lifecycle-continue' in arguments[8]:
                self.case += 1
        if arguments[3:7] == ('exec-out', 'run-as', BUNDLE, 'cat'):
            name = arguments[7]
            if name.endswith('phase.json'):
                self.tick += 1
                if self.partial:
                    self.partial = False
                    return subprocess.CompletedProcess(arguments, 0, b'{', b'')
                landscape = self.size == '2480x1860'
                rail = self.size in ('1860x2480', '2480x1860')
                data = json.dumps(dict(name=('navigation', 'canvas', 'speech')[self.case],
                    tick=self.tick, pid=17,
                    run_id='replacement' if self.restart and self.tick > 1 else 'original',
                    state=dict(mode='rail' if rail else 'bottom',
                    width=800 if landscape else 600 if rail else 400,
                    height=600 if landscape else 800))).encode()
            elif self.case == 3:
                events = ['show', 'hide', 'show', 'hide', 'show', 'hide', 'show'] if self.visible else ['show']
                data = json.dumps(dict(run_id='original', passed=self.passed,
                    cases=[dict(passed=self.passed)], visibility_events=events)).encode()
        return subprocess.CompletedProcess(arguments, 0, data, b'')


class NativeLifecycleToolTests(unittest.TestCase):
    def test_physical_android_device_is_rejected_before_commands(self):
        with TemporaryDirectory() as directory, patch(
                'mobile_build.validation.native_lifecycle_tools.subprocess.run') as command:
            with self.assertRaisesRegex(ValueError, 'dedicated Android emulator'):
                validate('android', 'physical-device', Path(directory))
            command.assert_not_called()

    def test_android_checks_resume_and_rail_then_cleans_up_even_after_partial_report(self):
        probe = AndroidProbe(partial=True)
        with TemporaryDirectory() as directory, patch(
                'mobile_build.validation.native_lifecycle_tools.subprocess.run', side_effect=probe), patch(
                'mobile_build.validation.native_lifecycle_tools.time.sleep'):
            output = Path(directory)
            result = validate('android', 'emulator-5580', output, adb='test-adb')
            self.assertTrue(result['passed'])
            self.assertEqual([check['case'] for check in result['external_checks']],
                ['1860x2480', '2480x1860', 'navigation-resume', 'canvas-resume', 'speech-resume'])
            self.assertEqual(json.loads((output / 'android-lifecycle.json').read_text()), result)
        self.assertTrue(all(call[:3] == ('test-adb', '-s', 'emulator-5580') for call in probe.calls))
        self.assertEqual(probe.calls[-3:], [
            ('test-adb', '-s', 'emulator-5580', 'shell', 'wm', 'size', 'reset'),
            ('test-adb', '-s', 'emulator-5580', 'shell', 'wm', 'density', 'reset'),
            ('test-adb', '-s', 'emulator-5580', 'shell', 'run-as', BUNDLE, 'rm', '-f',
             'cache/native-lifecycle-external')])
        self.assertNotEqual(BUNDLE, 'io.github.ispaure.logisticsmobile')
        self.assertFalse(any('install' in call or 'uninstall' in call for call in probe.calls))

    def test_failed_android_acceptance_keeps_report_and_restores_display(self):
        probe = AndroidProbe(passed=False)
        with TemporaryDirectory() as directory, patch(
                'mobile_build.validation.native_lifecycle_tools.subprocess.run', side_effect=probe), patch(
                'mobile_build.validation.native_lifecycle_tools.time.sleep'):
            output = Path(directory)
            with self.assertRaises(AssertionError):
                validate('android', 'emulator-5580', output)
            self.assertFalse(json.loads((output / 'android-lifecycle.json').read_text())['passed'])
        self.assertEqual(probe.calls[-3][-3:], ('wm', 'size', 'reset'))
        self.assertEqual(probe.calls[-2][-3:], ('wm', 'density', 'reset'))

    def test_missing_native_visibility_events_marks_saved_result_failed(self):
        probe = AndroidProbe(visible=False)
        with TemporaryDirectory() as directory, patch(
                'mobile_build.validation.native_lifecycle_tools.subprocess.run', side_effect=probe), patch(
                'mobile_build.validation.native_lifecycle_tools.time.sleep'):
            output = Path(directory)
            with self.assertRaises(AssertionError):
                validate('android', 'emulator-5580', output)
            result = json.loads((output / 'android-lifecycle.json').read_text())
            self.assertFalse(result['passed'])
            self.assertFalse(result['external_passed'])

    def test_same_process_probe_restart_is_rejected_and_display_is_restored(self):
        probe = AndroidProbe(restart=True)
        with TemporaryDirectory() as directory, patch(
                'mobile_build.validation.native_lifecycle_tools.subprocess.run', side_effect=probe), patch(
                'mobile_build.validation.native_lifecycle_tools.time.sleep'):
            with self.assertRaisesRegex(AssertionError, 'probe instance was replaced'):
                validate('android', 'emulator-5580', Path(directory))
        self.assertEqual(probe.calls[-3][-3:], ('wm', 'size', 'reset'))
        self.assertEqual(probe.calls[-2][-3:], ('wm', 'density', 'reset'))

    def test_early_ios_failure_keeps_report_and_removes_external_marker(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / 'container/Library/Caches'
            cache.mkdir(parents=True)
            report = dict(passed=False, cases=[dict(error='native assertion failed')])

            def command(arguments, **kwargs):
                data = b''
                if arguments[2] == 'get_app_container':
                    data = str(root / 'container').encode()
                elif arguments[2] == 'launch':
                    (cache / 'native-lifecycle.json').write_text(json.dumps(report))
                return subprocess.CompletedProcess(arguments, 0, data, b'')

            with patch('mobile_build.validation.native_lifecycle_tools.subprocess.run',
                    side_effect=command) as calls:
                with self.assertRaisesRegex(AssertionError, 'Probe finished before checkpoint'):
                    validate('ios', 'dedicated-simulator', root / 'evidence')
            self.assertEqual(json.loads((root / 'evidence/ios-lifecycle.json').read_text()), report)
            self.assertFalse((cache / 'native-lifecycle-external').exists())
            self.assertTrue(all(call.args[0][3] == 'dedicated-simulator' for call in calls.call_args_list))
            self.assertFalse(any('uninstall' in call.args[0] for call in calls.call_args_list))
