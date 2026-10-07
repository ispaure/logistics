"""FUSE commands, recovery and cleanup using simulated mount states."""

from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

from commonUtils.osUtils import OS
from features.fuse import mounts, commands, detection, actions, ui_contributions
from models.folder_entry import FolderEntry


class FuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.mount_path = self.root / 'Mount'
        self.executable = self.root / 'rclone with spaces'
        self.executable.touch()
        self.config_path = self.root / 'profile.conf'
        self.config_path.touch()
        for target, value in ((mounts, OS.MAC),):
            patcher = patch.object(target, 'get_os', return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for target, options in (
            ('features.fuse.mounts.log', {}),
            ('features.fuse.mounts.get_remote_mount_path', {'return_value': self.mount_path}),
            ('features.fuse.mounts.executable.get_rclone_path', {'return_value': self.executable}),
            ('features.fuse.mounts.configuration.get_rclone_remote_names', {'return_value': ['Mount']}),
        ):
            patcher = patch(target, **options)
            patcher.start()
            self.addCleanup(patcher.stop)

    def result(self, code=0, stdout='', stderr=''):
        return subprocess.CompletedProcess([], code, stdout, stderr)

    def test_argument_lists_preserve_quotes_spaces_and_shell_text(self):
        name = 'Books $(example)'
        for platform in (OS.MAC, OS.LINUX, OS.WIN):
            args = commands.mount_arguments(self.executable, name, self.config_path,
                                           self.mount_path, platform, 2)
            self.assertIn(name + ':', args)
            self.assertIn(str(self.executable), args)
            self.assertIn('--attr-timeout=2s', args)
            self.assertEqual('--daemon' in args, platform != OS.WIN)
        for bad in ('../Books', '/Books', 'Books/Other', 'C:Books', '..', 'Books\n', '--option', ''):
            with self.subTest(name=bad), self.assertRaises(ValueError):
                commands.validate_remote_name(bad)
        for bad in (-1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                commands.mount_arguments(self.executable, 'Mount', self.config_path,
                                         self.mount_path, OS.MAC, bad)

    def test_real_probe_reads_a_temporary_directory_without_a_shell(self):
        self.mount_path.mkdir()
        with patch.object(mounts, 'is_mount_path_mounted', return_value=True):
            self.assertTrue(mounts.is_mount_path_ready(self.mount_path))

    def test_readiness_handles_timeout_failed_command_and_missing_mount(self):
        with patch.object(mounts, 'is_mount_path_mounted', return_value=True):
            for outcome in (subprocess.TimeoutExpired(['probe'], 1), OSError('missing'),
                            self.result(1, commands.READY_MARKER), self.result(0, 'not ready')):
                with self.subTest(outcome=outcome), patch.object(
                        mounts.subprocess, 'run', side_effect=outcome if isinstance(outcome, Exception) else None,
                        return_value=outcome):
                    self.assertFalse(mounts.is_mount_path_ready(self.mount_path, 1))
        with patch.object(mounts, 'is_mount_path_mounted', return_value=False), patch.object(
                mounts.subprocess, 'run') as run:
            self.assertFalse(mounts.is_mount_path_ready(self.mount_path))
        run.assert_not_called()

    def test_failed_mount_command_does_not_report_success_and_cleans_empty_path(self):
        with patch.object(mounts, 'is_mount_path_mounted', return_value=False), patch.object(
                mounts.subprocess, 'run', return_value=self.result(1, stderr='failed')) as run:
            self.assertFalse(mounts.mount_remote('Mount', self.config_path, self.mount_path))
        self.assertFalse(self.mount_path.exists())
        self.assertEqual(run.call_args.args[0][0], str(self.executable))

    def test_missing_remote_and_nonempty_mount_do_not_start_a_process(self):
        self.mount_path.mkdir()
        (self.mount_path / 'keep').write_bytes(b'keep')
        with patch.object(mounts, 'is_mount_path_mounted', return_value=False), patch.object(
                mounts.subprocess, 'run') as run:
            self.assertFalse(mounts.mount_remote('Mount', self.config_path, self.mount_path))
            self.assertFalse(mounts.mount_remote('Missing', self.config_path, self.root / 'Missing'))
        run.assert_not_called()
        self.assertEqual((self.mount_path / 'keep').read_bytes(), b'keep')

    def test_windows_mount_is_started_without_daemon_flag(self):
        with patch.object(mounts, 'get_os', return_value=OS.WIN), patch.object(
                mounts, 'is_mount_path_mounted', return_value=False), patch.object(
                mounts.subprocess, 'Popen') as start:
            self.assertTrue(mounts.mount_remote('Mount', self.config_path, self.mount_path))
        self.assertNotIn('--daemon', start.call_args.args[0])

    def test_existing_ready_mount_does_not_launch_again(self):
        with patch.object(mounts, 'is_mount_path_mounted', return_value=True), patch.object(
                mounts, 'is_mount_path_ready', return_value=True), patch.object(
                mounts.subprocess, 'run') as run:
            self.assertTrue(mounts.mount_remote('Mount', self.config_path, self.mount_path))
        run.assert_not_called()

    def test_recovery_stops_if_unmount_fails(self):
        with patch.object(mounts, 'is_remote_ready', return_value=False), patch.object(
                mounts, 'is_remote_mounted', return_value=True), patch.object(
                mounts, 'unmount_remote', return_value=False), patch.object(mounts, 'mount_remote') as start:
            self.assertIsNone(mounts.ensure_remote_mounted('Mount', self.config_path))
        start.assert_not_called()

    def test_recovery_unmounts_stale_mount_then_returns_ready_path(self):
        with patch.object(mounts, 'is_remote_ready', return_value=False), patch.object(
                mounts, 'is_remote_mounted', return_value=True), patch.object(
                mounts, 'unmount_remote', return_value=True) as unmount, patch.object(
                mounts, 'mount_remote', return_value=True), patch.object(
                mounts, 'wait_until_remote_ready', return_value=True):
            self.assertEqual(mounts.ensure_remote_mounted('Mount', self.config_path), self.mount_path)
        unmount.assert_called_once_with('Mount')

    def test_failed_readiness_preserves_nonempty_mount_directory(self):
        self.mount_path.mkdir()
        (self.mount_path / 'keep').touch()
        with patch.object(mounts, 'is_remote_ready', return_value=False), patch.object(
                mounts, 'is_remote_mounted', return_value=False), patch.object(
                mounts, 'mount_remote', return_value=True), patch.object(
                mounts, 'wait_until_remote_ready', return_value=False):
            self.assertIsNone(mounts.ensure_remote_mounted('Mount', self.config_path))
        self.assertTrue((self.mount_path / 'keep').exists())

    def test_polling_passes_only_remaining_budget_to_probe(self):
        clock = [0.0]
        timeouts = []
        def probe(name, probe_timeout):
            timeouts.append(probe_timeout)
            clock[0] += probe_timeout
            return False
        with patch.object(mounts.time, 'monotonic', side_effect=lambda: clock[0]), patch.object(
                mounts.time, 'sleep', side_effect=lambda delay: clock.__setitem__(0, clock[0] + delay)), patch.object(
                mounts, 'is_remote_ready', side_effect=probe):
            self.assertFalse(mounts.wait_until_remote_ready('Mount', 0.5))
        self.assertEqual(timeouts, [0.5])
        self.assertEqual(clock[0], 0.5)

    def test_invalid_wait_budgets_are_rejected_before_mounting(self):
        for budget in (float('inf'), float('nan'), -1):
            with self.subTest(budget=budget), patch.object(mounts, 'mount_remote') as start:
                with self.assertRaises(ValueError):
                    mounts.ensure_remote_mounted('Mount', self.config_path, wait_timeout=budget)
                with self.assertRaises(ValueError):
                    mounts.mount_all_rclone_conf_remotes(self.config_path, wait_timeout=budget)
                start.assert_not_called()

    def test_bulk_wait_stops_when_remote_is_not_ready(self):
        with patch.object(mounts, 'get_rclone_remote_mount_paths', return_value=[str(self.mount_path)]), patch.object(
                mounts, 'mount_remote', return_value=True), patch.object(
                mounts, 'wait_until_remote_ready', return_value=False) as wait:
            self.assertFalse(mounts.mount_all_rclone_conf_remotes(self.config_path, wait_until_mounted=True, wait_timeout=1))
        self.assertLessEqual(wait.call_args.kwargs['timeout'], 1)

    def test_windows_startup_only_removes_empty_ordinary_directories(self):
        empty = self.root / 'empty'
        empty.mkdir()
        occupied = self.root / 'occupied'
        occupied.mkdir()
        (occupied / 'keep').touch()
        linked = self.root / 'linked'
        linked.symlink_to(occupied, target_is_directory=True)
        active = self.root / 'active'
        active.mkdir()
        with patch.object(mounts, 'get_os', return_value=OS.WIN), patch.object(
                mounts.config, 'LogisticsConfig', return_value=SimpleNamespace(path_remote_network_mount=self.root)), patch.object(
                mounts.os.path, 'ismount', side_effect=lambda path: path == active):
            mounts.clear_mounts()
        self.assertFalse(empty.exists())
        self.assertTrue(occupied.exists())
        self.assertTrue(linked.is_symlink())
        self.assertTrue(active.exists())

    def test_linux_dependency_lookup_does_not_require_private_resources(self):
        with patch.object(detection, 'get_os', return_value=OS.LINUX), patch.object(
                detection.config, 'LogisticsConfig') as settings:
            self.assertIsNone(detection.get_installer_path())
        settings.assert_not_called()

    def test_folder_action_discovery_is_lazy(self):
        entry = FolderEntry('Mount', remote_name='Mount', remote_source='rclone', remote_context=self.config_path)
        with patch.object(actions, 'mount_and_open_remote') as open_remote:
            self.assertTrue(ui_contributions._is_available(entry))
            offered = ui_contributions._get_actions(entry)
            open_remote.assert_not_called()
            offered[0].callback()
        open_remote.assert_called_once_with('Mount', self.config_path)

    def test_failed_linux_unmount_does_not_cleanup_directory(self):
        self.mount_path.mkdir()
        with patch.object(mounts, 'get_os', return_value=OS.LINUX), patch.object(
                mounts, 'is_mount_path_mounted', return_value=True), patch.object(
                mounts.shutil, 'which', return_value='/usr/bin/fusermount3'), patch.object(
                mounts.subprocess, 'run', return_value=self.result(1, stderr='busy')) as run:
            self.assertFalse(mounts.unmount_remote('Mount'))
        self.assertEqual(run.call_args.args[0], ['/usr/bin/fusermount3', '-u', str(self.mount_path)])
        self.assertTrue(self.mount_path.exists())

    def test_successful_unmount_at_deadline_is_recognized(self):
        self.mount_path.mkdir()
        clock = [0.0]
        def unmount(*args, **kwargs):
            clock[0] = 5
            return self.result()
        with patch.object(mounts, 'is_mount_path_mounted', side_effect=[True, False]), patch.object(
                mounts.subprocess, 'run', side_effect=unmount), patch.object(
                mounts.time, 'monotonic', side_effect=lambda: clock[0]):
            self.assertTrue(mounts.unmount_remote('Mount', 5))
        self.assertFalse(self.mount_path.exists())

    def test_unmount_wait_is_bounded_when_mount_stays_present(self):
        clock = [0.0]
        with patch.object(mounts, 'is_mount_path_mounted', return_value=True), patch.object(
                mounts.subprocess, 'run', return_value=self.result()), patch.object(
                mounts.time, 'monotonic', side_effect=lambda: clock[0]), patch.object(
                mounts.time, 'sleep', side_effect=lambda delay: clock.__setitem__(0, clock[0] + delay)):
            self.assertFalse(mounts.unmount_remote('Mount', 0.5))
        self.assertAlmostEqual(clock[0], 0.5)

    def test_installer_launch_failure_is_reported_without_mounting(self):
        with patch.object(actions, 'get_os', return_value=OS.MAC), patch.object(
                actions.detection, 'get_installer_path', return_value=self.executable), patch.object(
                actions.subprocess, 'Popen', side_effect=OSError('launch failed')), patch.object(
                actions.ui, 'display_msg_box_ok') as message:
            self.assertFalse(actions.launch_installer())
        self.assertIn('launch failed', message.call_args.args[1])
