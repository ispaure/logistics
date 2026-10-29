"""A crashed next device cannot retain the previous device's success artifacts."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from mobile_build.validation import ui_tools


class NativeReportIsolationTests(unittest.TestCase):
    def test_failed_next_device_removes_prior_reports_but_preserves_other_owners(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            logs = root / 'logs'
            logs.mkdir()
            stale = ['ios-native-ui' + suffix for suffix in (
                '.json', '-local.json', '-stdout.json', '-cached.json',
                '-error.txt', '-fault.log', '-timings.json')]
            stale.append('ios-report-transport.json')
            for name in (*stale, 'android-native-ui.json', 'unrelated.txt'):
                (logs / name).write_text('previous device')
            previous = Path.cwd()
            try:
                os.chdir(root)
                with patch.object(ui_tools.subprocess, 'Popen', return_value=Mock(wait=Mock(return_value=200))), patch.object(
                        ui_tools, 'read_report', side_effect=ValueError('No current report')), patch.object(
                        ui_tools, 'simulator_report', return_value=None):
                    with self.assertRaisesRegex(RuntimeError, r'failed \(200\)'):
                        ui_tools.run('ios', 'new-owned-device')
            finally:
                os.chdir(previous)
            self.assertTrue(all(not (logs / name).exists() for name in stale))
            self.assertEqual((logs / 'android-native-ui.json').read_text(), 'previous device')
            self.assertEqual((logs / 'unrelated.txt').read_text(), 'previous device')
