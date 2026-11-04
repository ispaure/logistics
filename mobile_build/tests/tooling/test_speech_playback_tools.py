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
