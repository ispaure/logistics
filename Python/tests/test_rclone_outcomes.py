"""Preview cannot run a live sync; synchronous and terminal failures reach callers."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.integrations.wrappers.cmdShellWrapper import CommandResult
from features.rclone import sync


class RcloneOutcomeTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.destination = Path(temp.name)/'uncreated'
        patcher = patch.object(sync.executable, 'ensure_rclone', return_value='/fake/rclone')
        patcher.start(); self.addCleanup(patcher.stop)

    def test_preview_forces_dry_run_without_creating_destination(self):
        with patch.object(sync.cmdShellWrapper, 'run_command', return_value=CommandResult(0)) as run:
            self.assertEqual(sync.rclone_sync('Remote:', self.destination, config_path='/fake/config', query=True), {'COPY': []})
        self.assertIn('--dry-run', run.call_args.args[0])
        self.assertFalse(self.destination.exists())

    def test_preview_failure_is_not_an_empty_successful_preview(self):
        with patch.object(sync.cmdShellWrapper, 'run_command', return_value=CommandResult(9, stderr=('failed',))):
            with self.assertRaisesRegex(RuntimeError, 'failed'):
                sync.rclone_sync('Remote:', self.destination, config_path='/fake/config', query=True)

    def test_synchronous_exit_failure_and_terminal_launch_failure(self):
        with patch.object(sync, 'log'), patch.object(sync.cmdShellWrapper, 'run_command', return_value=CommandResult(7)) as run:
            self.assertFalse(sync.rclone_sync('Remote:', self.destination, config_path='/fake/config', wait_for_output=True))
            self.assertIsInstance(run.call_args.args[0], list)
        with patch.object(sync.cmdShellWrapper, 'exec_cmd', return_value=False):
            self.assertFalse(sync.rclone_sync('Remote:', self.destination, config_path='/fake/config', integrated=False))

    def test_preflighted_worker_path_never_opens_provisioning_ui(self):
        with patch.object(sync.executable, 'ensure_rclone') as provision, patch.object(
                sync.cmdShellWrapper, 'run_command', return_value=CommandResult(0)) as run:
            self.assertTrue(sync.rclone_sync('Remote:', self.destination, config_path='/fake/config',
                            wait_for_output=True, executable_path='/already-installed/rclone'))
        provision.assert_not_called()
        self.assertEqual(run.call_args.args[0][0], '/already-installed/rclone')
