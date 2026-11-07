"""The focused native driver requires a real relaunch of the isolated QA app."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from mobile_build.validation import document_storage_tools as driver


class UnifiedProgressDriverTests(unittest.TestCase):
    def test_same_pid_and_replayed_checkpoints_are_rejected(self):
        for report in (dict(phase='restarted', pid=41), dict(phase='checkpoint', pid=42)):
            with self.subTest(report=report), self.assertRaisesRegex(ValueError, 'phase/process'):
                driver.check_progress_report(report, 41)

    def test_initial_report_requires_a_checkpoint_from_a_real_pid(self):
        for report in (dict(phase='restarted', pid=41), dict(phase='checkpoint', pid=True)):
            with self.subTest(report=report), self.assertRaises(ValueError):
                driver.check_progress_report(report, None)

    def test_checkpoint_triggers_termination_and_relaunch_before_terminal_report(self):
        for entry_point in (driver.UNIFIED_PROGRESS_ENTRY, driver.UNIFIED_PROGRESS_VIDEO_ENTRY):
            with self.subTest(entry_point=entry_point):
                self.check_ios_relaunch(entry_point)

    def check_ios_relaunch(self, entry_point):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / 'container/Library/Caches'
            cache.mkdir(parents=True)
            report = cache / driver.UNIFIED_PROGRESS_RESULT
            output = root / 'evidence'
            initial = dict(success=True, phase='checkpoint', pid=41)
            capture_name = 'progress-fixture-epub-before' if entry_point == driver.UNIFIED_PROGRESS_ENTRY else None
            final = dict(success=True, phase='restarted', pid=42)
            events = []
            client = Mock()
            client.devices.return_value = {'devices': {'ios': [
                dict(name='iPhone Duo', isAvailable=True, deviceTypeIdentifier='duo')]}}
            client.create.return_value = 'owned-simulator'

            def invoke(action, device, *arguments, **kwargs):
                self.assertEqual(device, 'owned-simulator')
                if action == 'get_app_container':
                    return str(root / 'container')
                if action == 'terminate':
                    self.assertEqual(arguments, (driver.UNIFIED_PROGRESS_BUNDLE,))
                    self.assertEqual(json.loads((output / 'ios-progress-before-restart.json').read_text()), initial)
                    self.assertFalse(report.exists())
                    if capture_name is not None:
                        self.assertTrue((cache / (capture_name + '.captured')).exists())
                    events.append('terminate')

            def launch(arguments, **kwargs):
                self.assertEqual(arguments[-2:], ['owned-simulator', driver.UNIFIED_PROGRESS_BUNDLE])
                self.assertIn(events, ([], ['launch', 'terminate']))
                if not events and capture_name is not None:
                    (cache / 'unified-progress-capture.json').write_text(json.dumps({'name': capture_name}))
                report.write_text(json.dumps(initial if not events else final))
                events.append('launch')
                return Mock()

            client.invoke.side_effect = invoke
            with patch.object(driver, 'AppleSimulators', return_value=client), \
                    patch.object(driver.subprocess, 'Popen', side_effect=launch), \
                    patch.object(driver.time, 'sleep'), patch.object(driver, 'cleanup_ios_probe') as cleanup:
                result = driver.exercise_ios_app(root / 'isolated.app', output, {},
                    bundle=driver.UNIFIED_PROGRESS_BUNDLE, entry_point=entry_point,
                    result_name=driver.UNIFIED_PROGRESS_RESULT, family='iPhone Duo')
            self.assertEqual(events, ['launch', 'terminate', 'launch'])
            self.assertEqual(result, final)
            self.assertEqual(json.loads((output / 'ios-result.json').read_text()), final)
            self.assertEqual(cleanup.call_args.args[1], 'owned-simulator')
            self.assertEqual(cleanup.call_args.args[2], client.create.call_args.args[0])
            self.assertEqual(cleanup.call_args.args[3], driver.UNIFIED_PROGRESS_BUNDLE)
