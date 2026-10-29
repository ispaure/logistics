"""All private CLI paths enforce the same cancellation and revocation boundary."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from unittest.mock import Mock, patch
import unittest

from commonUtils.runtime.operations import OperationCancelled
from commonUtils.runtime.resources.lifetime import WorkerCancellation
from features.rclone import session
from features.rclone.localcrypt.transport import CryptCommand


class CryptCommandTests(unittest.TestCase):
    def setUp(self):
        self.context = Path('/synthetic/private.session')
        self.scope = WorkerCancellation()
        self.validate = Mock()
        self.command = CryptCommand(Path('/synthetic/rclone'), self.context, self.scope,
                                    self.validate, closed=lambda: False)

    def test_cancelled_command_is_refused_before_session_launch(self):
        with patch.object(session, 'revocation_check', return_value=lambda: False), \
             patch.object(session, 'launch') as launch:
            with self.assertRaises(OperationCancelled):
                self.command.command('cat', 'private.md', cancelled=lambda: True)
            launch.assert_not_called()

    def test_encoding_honors_worker_cancellation_before_launch(self):
        with patch.object(session, 'revocation_check', return_value=lambda: False), \
             patch.object(session, 'launch') as launch, self.scope.scope(lambda: True):
            with self.assertRaises(OperationCancelled):
                self.command.encode('private.md')
            launch.assert_not_called()

    def test_replaced_generation_rejects_result_even_when_process_returns_bytes(self):
        revoked = False
        def run(*args, **kwargs):
            nonlocal revoked
            revoked = True
            self.assertTrue(kwargs['cancelled']())
            return b'private bytes'
        with patch.object(session, 'revocation_check', return_value=lambda: revoked), \
             patch.object(session, 'launch', return_value=({}, 'view:private.md', '')), \
             patch('features.rclone.localcrypt.transport.run_bytes', side_effect=run):
            with self.assertRaises(OperationCancelled):
                self.command.command('cat', 'private.md')

    def test_command_passes_null_config_environment_and_bounds_to_process(self):
        environment = {'SYNTHETIC_CREDENTIAL': 'memory only'}
        with patch.object(session, 'revocation_check', return_value=lambda: False), \
             patch.object(session, 'launch', return_value=(environment, 'view:note.md', '')) as launch, \
             patch('features.rclone.localcrypt.transport.run_bytes', return_value=b'abc') as run:
            self.assertEqual(self.command.command('cat', 'note.md', '--count', '3', limit=3), b'abc')
        launch.assert_called_once_with(self.context, 'view:note.md', '')
        self.assertEqual(run.call_args.args[0][-4:], ['cat', 'view:note.md', '--count', '3'])
        self.assertEqual(run.call_args.args[0][1:3], ['--config', session.NULL_CONFIG])
        self.assertIs(run.call_args.kwargs['environment'], environment)
        self.assertEqual(run.call_args.kwargs['max_output'], 3)
        self.assertEqual(self.validate.call_count, 2)

    def test_encode_rejects_incomplete_or_ambiguous_results(self):
        with patch.object(session, 'revocation_check', return_value=lambda: False), \
             patch.object(session, 'launch', return_value=({}, 'view:', '')), \
             patch('features.rclone.localcrypt.transport.run_bytes') as run:
            for reply in (b'[]', b'["one","two"]', b'{}', b'[null]', b'[123]'):
                run.return_value = reply
                with self.assertRaisesRegex(ValueError, 'could not be resolved'):
                    self.command.encode('private.md')
