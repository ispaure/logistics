"""Desktop service adapters retain captured access across launch hooks."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from commonUtils.runtime.operations import OperationCancelled
from features.rclone import session
from features.rclone.desktop_service import service
from features.rclone.transfers.desktop import DesktopTransferRequest
from features.rclone.transfers.transfer_options import TransferOptions


class DesktopTransferTests(unittest.TestCase):
    def approve(self, prepared):
        self.assertTrue(prepared.review.scan.retired.wait(2))
        self.assertTrue(prepared.review.approve())
        self.assertTrue(prepared.review.scan.retired.wait(2))
        self.assertTrue(prepared.review.approved)

    def test_replacement_in_launch_hook_cannot_start_an_engine_with_new_access(self):
        with TemporaryDirectory() as root:
            config = Path(root) / 'account.session'
            values = {'Files': {'type': 'local'}}
            session.remember(config, values)
            self.addCleanup(session.forget, config)
            transfer = DesktopTransferRequest(root, 'Files:', 'Push', config, Path('/rclone'),
                before_start=lambda: session.remember(config, values))
            with patch('features.rclone.localcrypt.backend.for_path', return_value=None), patch(
                    'features.rclone.transfers.desktop.scanner', return_value=lambda emit, cancelled: 'revision'), patch(
                    'features.rclone.transfers.sync.rclone_sync') as execute:
                prepared = service.transfers.review(transfer)
                self.approve(prepared)
                with self.assertRaises(OperationCancelled):
                    service.transfers.execute(prepared)
                execute.assert_not_called()
                with self.assertRaisesRegex(ValueError, 'already used'):
                    service.transfers.execute(prepared)

    def test_launch_flags_and_options_are_snapshots(self):
        with TemporaryDirectory() as root:
            config = Path(root) / 'account.session'
            session.remember(config, {'Files': {'type': 'local'}})
            self.addCleanup(session.forget, config)
            launch = dict(wait_for_output=True)
            options = TransferOptions(bw_limit=3, excludes=('*.tmp',))
            transfer = DesktopTransferRequest(root, 'Files:', 'Push', config, Path('/rclone'), options, launch=launch)
            launch['wait_for_output'] = False
            with patch('features.rclone.localcrypt.backend.for_path', return_value=None), patch(
                    'features.rclone.transfers.desktop.scanner', return_value=lambda emit, cancelled: 'revision'), patch(
                    'features.rclone.transfers.sync.rclone_sync', return_value=True) as execute:
                prepared = service.transfers.review(transfer)
                self.approve(prepared)
                self.assertTrue(service.transfers.execute(prepared))
                self.assertEqual(execute.call_args.kwargs['bw_limit'], 3)
                self.assertEqual(execute.call_args.kwargs['excludes'], ('*.tmp',))
                self.assertTrue(execute.call_args.kwargs['wait_for_output'])

    def test_saved_config_snapshots_retire_with_scans_and_the_launched_process(self):
        with TemporaryDirectory() as root:
            config = Path(root) / 'account.conf'
            original = '[Files]\ntype = local\n'
            config.write_text(original)
            transfer = DesktopTransferRequest(root, 'Files:', 'Push', config, Path('/rclone'))
            comparisons, executions, completions = [], [], []
            def scanner(binary, source, destination, context, options, **kwargs):
                comparisons.append(context)
                self.assertEqual(session.credentials(context), {'Files': {'type': 'local'}})
                return lambda emit, cancelled: 'revision'
            def execute(*args, **kwargs):
                context = kwargs['config_path']
                executions.append(context)
                self.assertEqual(session.credentials(context), {'Files': {'type': 'local'}})
                window = Mock(busy=True)
                window.runner.completed.connect.side_effect = completions.append
                kwargs['on_launch'](window)
                return True
            with patch('features.rclone.localcrypt.backend.for_path', return_value=None), patch(
                    'features.rclone.transfers.desktop.scanner', side_effect=scanner), patch(
                    'features.rclone.transfers.sync.rclone_sync', side_effect=execute):
                prepared = service.transfers.review(transfer)
                self.approve(prepared)
                self.assertEqual(len(comparisons), 2)
                for context in comparisons:
                    self.assertIsNone(session.credentials(context))
                self.assertTrue(service.transfers.execute(prepared))
                context = executions[0]
                self.addCleanup(session.forget, context)
                self.assertIsNotNone(session.credentials(context))
                completions[0]()
                self.assertIsNone(session.credentials(context))
                self.assertEqual(config.read_text(), original)
