"""Bounded server diagnostics cannot sample unrelated or unowned processes."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
import importlib.util
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('screen_time_rpc', Path(__file__).resolve().parents[2] / 'validation/screen_time_rpc.py')
rpc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rpc)
DEVICE = '12345678-1234-1234-1234-123456789abc'
NAME = 'Logistics Native Gate ' + 'a' * 32
PROGRAM = '/Runtime/System/Library/PrivateFrameworks/ScreenTimeSettingsFoundation.framework/ScreenTimeSettingsAgent'
EXE = '/Library/Developer/CoreSimulator/Devices/' + DEVICE + '/data/Containers/Bundle/Application/abcdef/Logistics Mobile.app/Logistics Mobile'

class ScreenTimeRPCDiagnosticsTests(unittest.TestCase):
    def fixture(self, directory, *, program=PROGRAM, sample_timeout=False):
        logs = Path(directory)
        (logs / 'ios-native-ui-owned.json').write_text(json.dumps(dict(device=DEVICE, name=NAME, removed=False)))
        calls = []
        def runner(args, **kwargs):
            calls.append(args)
            self.assertLessEqual(kwargs['timeout'], 15)
            self.assertTrue(kwargs['capture_output'])
            if args[0] == 'sample':
                if sample_timeout:
                    raise subprocess.TimeoutExpired(args, kwargs['timeout'])
                Path(args[-1]).write_text('Call graph:\n Thread_55 DispatchQueue_1\n')
                text = ''
            elif args[:4] == ['xcrun', 'simctl', 'list', 'devices']:
                text = json.dumps(dict(devices={'runtime': [dict(udid=DEVICE, name=NAME, state='Booted')]}))
            elif 'launchctl' in args:
                text = 'state = running\nprogram = ' + program + '\npid = 5678\n'
            elif args[-1] == 'comm=':
                text = program
            else:
                text = '5678 1 S 0.0 1024 ' + program
            return subprocess.CompletedProcess(args, 0, text, '')
        return logs, calls, runner

    def test_captures_only_owned_simulator_service_and_retains_app_pid(self):
        with TemporaryDirectory() as directory:
            logs, calls, runner = self.fixture(directory)
            result = rpc.capture(logs / 'ios-native-ui.log', EXE, 1234, runner=runner)
            self.assertEqual(result['status'], 'sampled')
            self.assertTrue(result['thread_stacks_present'])
            self.assertEqual(result['pid'], 5678)
            self.assertTrue((logs / 'ios-screen-time-rpc-1234.json').exists())
            self.assertEqual(sum(args[0] == 'sample' for args in calls), 1)
            self.assertFalse(any('kill' in args or 'kickstart' in args for args in calls))

    def test_missing_owner_never_invokes_process_tools(self):
        with TemporaryDirectory() as directory:
            calls = []
            result = rpc.capture(Path(directory) / 'ios-native-ui.log', EXE, 1234,
                                 runner=lambda *a, **k: calls.append(a))
            self.assertEqual(result['status'], 'capture-error')
            self.assertEqual(calls, [])

    def test_unexpected_service_program_is_not_sampled(self):
        with TemporaryDirectory() as directory:
            logs, calls, runner = self.fixture(directory, program='/Applications/Unrelated')
            result = rpc.capture(logs / 'ios-native-ui.log', EXE, 1234, runner=runner)
            self.assertEqual(result['status'], 'capture-error')
            self.assertFalse(any(args[0] == 'sample' for args in calls))

    def test_sample_timeout_is_retained_as_diagnostic_failure(self):
        with TemporaryDirectory() as directory:
            logs, calls, runner = self.fixture(directory, sample_timeout=True)
            result = rpc.capture(logs / 'ios-native-ui.log', EXE, 1234, runner=runner)
            self.assertEqual(result['status'], 'capture-error')
            self.assertIn('TimeoutExpired', result['error'])

    def test_collects_both_sides_of_service_candidates_without_environment_dumps(self):
        with TemporaryDirectory() as directory:
            logs, calls, original = self.fixture(directory)
            programs = {5678: PROGRAM,
                6789: '/Runtime/System/Library/PrivateFrameworks/ScreenTimeCore.framework/ScreenTimeAgent',
                7890: '/Runtime/System/Library/CoreServices/SpringBoard.app/SpringBoard'}
            (logs / 'ios-webkit-live.log').write_text('old' + 'x' * (1024 * 1024) + '\nconnection timeline\n')
            def runner(args, **kwargs):
                if 'launchctl' in args:
                    calls.append(args)
                    label = args[-1]
                    if label in ('user/foreground', 'system'):
                        text = 'com.apple.ScreenTimeSettings.settings-service\nenvironment = { PRIVATE_TOKEN=secret }'
                    else:
                        key = (5678 if label.endswith('/com.apple.ScreenTimeSettingsAgent') else
                            6789 if label.endswith(('/com.apple.ScreenTimeAgent', '/com.apple.ScreenTimeSettings.settings-service')) else
                            7890 if label.endswith('/com.apple.SpringBoard') else None)
                        if key is None:
                            return subprocess.CompletedProcess(args, 113, '', '')
                        text = f'state = running\nprogram = {programs[key]}\npid = {key}\nendpoints = {{ com.apple.ScreenTimeSettings.settings-service }}\nenvironment = {{ PRIVATE_TOKEN=secret }}'
                    return subprocess.CompletedProcess(args, 0, text, '')
                if args[0] == 'ps':
                    calls.append(args)
                    return subprocess.CompletedProcess(args, 0, programs[int(args[args.index('-p') + 1])], '')
                if args[:4] == ['xcrun', 'simctl', 'list', 'runtimes']:
                    return subprocess.CompletedProcess(args, 0, json.dumps(dict(runtimes=[dict(identifier='runtime', version='27.0', buildversion='fixture-build')])), '')
                return original(args, **kwargs)
            result = rpc.capture(logs / 'ios-native-ui.log', EXE, 1234, runner=runner)
            self.assertEqual(result['status'], 'sampled')
            self.assertEqual({row['pid'] for row in result['services'] if row['status'] == 'sampled'}, {5678, 6789, 7890})
            self.assertEqual(sum(args[0] == 'sample' for args in calls), 3)
            self.assertEqual(result['runtime']['buildversion'], 'fixture-build')
            self.assertNotIn('PRIVATE_TOKEN', json.dumps(result))
            timeline = logs / 'ios-screen-time-rpc-1234.timeline.log'
            self.assertEqual(timeline.stat().st_size, 1024 * 1024)
            self.assertTrue(timeline.read_text().endswith('connection timeline\n'))
            self.assertFalse(any('kill' in args or 'kickstart' in args for args in calls))

    def test_total_capture_budget_stops_further_process_operations(self):
        with TemporaryDirectory() as directory:
            logs, calls, runner = self.fixture(directory)
            with patch.object(rpc.time, 'monotonic', side_effect=[0, 41]):
                result = rpc.capture(logs / 'ios-native-ui.log', EXE, 1234, runner=runner)
            self.assertEqual(result['status'], 'capture-error')
            self.assertIn('budget expired', result['error'])
            self.assertEqual(calls, [])
