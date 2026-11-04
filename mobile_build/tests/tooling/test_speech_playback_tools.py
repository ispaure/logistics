"""Runtime comparisons must select a fresh compatible disposable simulator."""
import unittest
from commonUtils.testing.stages import TestStage
from mobile_build.validation.document_storage_tools import simulator_selection

TEST_STAGE = TestStage.REGRESSION


class SpeechPlaybackToolsTests(unittest.TestCase):
    def test_explicit_runtime_never_falls_back_to_another_os(self):
        row = lambda name, model, available=True: dict(name=name, deviceTypeIdentifier=model, isAvailable=available)
        inventory = {'new': [row('iPhone Duo', 'duo'), row('iPhone 17', 'phone')],
                     'older': [row('iPhone 16', 'old', False), row('iPhone 16 Pro', 'old-pro')]}
        self.assertEqual(simulator_selection(inventory, 'iPhone'), ('new', 'phone'))
        self.assertEqual(simulator_selection(inventory, 'iPhone', 'older'), ('older', 'old-pro'))
        with self.assertRaisesRegex(ValueError, 'runtime missing'):
            simulator_selection(inventory, 'iPhone', 'missing')
        with self.assertRaisesRegex(ValueError, 'iPad'):
            simulator_selection(inventory, 'iPad', 'older')

    def test_unavailable_native_engine_cannot_pass_playback_acceptance(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from types import SimpleNamespace
        from commonUtils.testing.event_loop import close_loop
        from mobile.app import LogisticsMobile
        from mobile_build.native_tests.tests.logisticsmobile.speech_playback_probe import SpeechPlaybackProbe
        class HostProbe(SpeechPlaybackProbe):
            def startup(self):
                LogisticsMobile.startup(self)
            def on_running(self):
                pass
            async def screenshot(self, name):
                pass
        with TemporaryDirectory() as directory:
            root = Path(directory)
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = HostProbe('Strict speech QA', 'io.github.ispaure.logisticsnotebookqa')
            app._paths = SimpleNamespace(cache=root)
            try:
                app.loop.run_until_complete(app.probe())
                report = json.loads((root / 'speech-playback-result.json').read_text())
                self.assertFalse(report['success'])
                self.assertIn('requires an Android or iOS speech engine', report['error'])
                self.assertNotIn('callbacks', report)
            finally:
                app.main_window.close()
                close_loop(app.loop)

    def test_native_app_shutdown_timeouts_still_remove_owned_simulator(self):
        from pathlib import Path
        import json
        import subprocess
        from tempfile import TemporaryDirectory
        from unittest.mock import Mock, call
        from mobile_build.validation.document_storage_tools import cleanup_ios_probe
        client = Mock()
        client.invoke.side_effect = subprocess.TimeoutExpired('simctl', 10)
        client.matching.side_effect = [dict(name='owned-name'), None]
        with TemporaryDirectory() as directory:
            cleanup_ios_probe(client, 'owned-device', 'owned-name', 'qa.bundle', Path(directory), installed=True)
            client.remove.assert_called_once_with('owned-device', 'owned-name')
            self.assertEqual(client.invoke.call_args_list,
                [call('terminate', 'owned-device', 'qa.bundle', timeout=10),
                 call('uninstall', 'owned-device', 'qa.bundle', timeout=10)])
            report = json.loads((Path(directory) / 'ios-cleanup.json').read_text())
            self.assertTrue(report['removed'])
            self.assertEqual(len(report['app_cleanup_errors']), 2)

    def test_cleanup_checks_ownership_before_any_app_operation(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import Mock
        from mobile_build.validation.document_storage_tools import cleanup_ios_probe
        client = Mock()
        client.matching.side_effect = ValueError('ownership mismatch')
        with TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, 'ownership'):
            cleanup_ios_probe(client, 'device', 'owned-name', 'qa.bundle', Path(directory), installed=True)
        client.invoke.assert_not_called()
        client.remove.assert_not_called()


class IOSProbeLaunchTests(unittest.TestCase):
    def exercise(self, exit_code, *, initial=None, delayed=None):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import Mock, patch
        from mobile_build.validation import document_storage_tools as tools
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / 'container/Library/Caches'
            cache.mkdir(parents=True)
            report = cache / 'fixture-result.json'
            if initial is not None:
                report.write_text(json.dumps(initial))
            client = Mock()
            client.devices.return_value = {'devices': {'runtime': [dict(name='iPhone Duo',
                deviceTypeIdentifier='owned-model', isAvailable=True)]}}
            client.create.return_value = 'owned-device'
            client.matching.side_effect = [dict(name='owned-name'), None]
            client.invoke.side_effect = lambda *args, **kwargs: str(root / 'container') if args[0] == 'get_app_container' else ''
            console = Mock()
            console.poll.return_value = exit_code
            def later(*args):
                if delayed is None:
                    raise AssertionError('Failed launch must not keep waiting.')
                report.write_text(json.dumps(delayed))
            with patch.object(tools, 'AppleSimulators', return_value=client), \
                    patch.object(tools.subprocess, 'Popen', return_value=console), \
                    patch.object(tools.time, 'sleep', side_effect=later) as sleep:
                try:
                    value = tools.exercise_ios_app(root / 'QA.app', root / 'output', {},
                        family='iPhone Duo', result_name='fixture-result.json')
                    return value, sleep.call_count, console.poll.call_count
                except RuntimeError:
                    if initial is None and exit_code not in (None, 0):
                        failure = json.loads((root / 'output/ios-launch-failure.json').read_text())
                        self.assertEqual(failure['exit_code'], exit_code)
                        self.assertEqual(failure['stage'], 'simctl-launch-before-result')
                    raise
                finally:
                    client.remove.assert_called_once()
                    self.assertTrue(json.loads((root / 'output/ios-cleanup.json').read_text())['removed'])
                    if initial is None and exit_code not in (None, 0):
                        sleep.assert_not_called()

    def test_failed_console_fails_immediately_and_cleans_owned_device(self):
        for exit_code in (5, -9):
            with self.subTest(exit_code=exit_code), self.assertRaisesRegex(RuntimeError, 'simctl launch console exited'):
                self.exercise(exit_code)

    def test_completed_result_wins_over_later_console_failure(self):
        value, sleeps, polls = self.exercise(5, initial={'success': True})
        self.assertTrue(value['success'])
        self.assertEqual((sleeps, polls), (0, 0))

    def test_app_report_failure_keeps_primary_cause(self):
        with self.assertRaisesRegex(RuntimeError, 'actual notebook assertion'):
            self.exercise(5, initial={'success': False, 'error': 'actual notebook assertion'})

    def test_successful_detached_console_still_waits_for_actual_result(self):
        value, sleeps, polls = self.exercise(0, delayed={'success': True})
        self.assertTrue(value['success'])
        self.assertEqual(sleeps, 1)

    def test_running_console_waits_for_actual_result(self):
        value, sleeps, polls = self.exercise(None, delayed={'success': True})
        self.assertTrue(value['success'])
        self.assertEqual(sleeps, 1)
