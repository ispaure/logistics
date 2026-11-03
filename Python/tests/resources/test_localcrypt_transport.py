"""All private CLI paths enforce the same cancellation and revocation boundary."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from unittest.mock import Mock, patch
import unittest
import json
import os

from commonUtils.runtime.operations import OperationCancelled
from commonUtils.runtime.resources.lifetime import WorkerCancellation
from features.rclone import session
from features.rclone.localcrypt.transport import CryptCommand


class CryptCommandTests(unittest.TestCase):
    def test_shared_batches_deduplicate_preserve_order_and_bound_long_paths(self):
        from features.rclone.localcrypt.path_batches import map_path_entries
        calls = []
        def resolve(batch):
            calls.append(list(batch))
            return [path + ('/directory' if directory else '/file') for path, directory in batch]
        entries = [('long/' + str(i) + '/' + 'é' * 300, False) for i in range(70)]
        entries += [entries[0], (entries[0][0], True)]
        result = map_path_entries(entries, resolve, check=lambda: None)
        self.assertGreater(len(calls), 1)
        self.assertEqual(sum(map(len, calls)), 71)
        self.assertEqual(result[0], result[-2])
        self.assertNotEqual(result[0], result[-1])
        self.assertTrue(all(sum(2 * len(path.encode('utf-8')) + 64 for path, _ in batch) <= 24 * 1024
                            for batch in calls))

    def test_shared_batches_reject_partial_results_and_revocation(self):
        from features.rclone.localcrypt.path_batches import map_path_entries
        for result in ([], [None], [''], ['one', 'two'], 'one'):
            with self.subTest(result=result), self.assertRaises(ValueError):
                map_path_entries([('one', False)], lambda batch: result, check=lambda: None)
        closed = False
        def check():
            if closed:
                raise ValueError('revoked')
        def revoke(batch):
            nonlocal closed
            closed = True
            return ['one']
        with self.assertRaisesRegex(ValueError, 'revoked'):
            map_path_entries([('one', False)], revoke, check=check)

    def test_encoding_and_decoding_share_deduplicated_bounded_processes(self):
        def run(arguments, path, **kwargs):
            command = arguments('view:')
            self.assertEqual(command[3:5], ['--json', '--'])
            return json.dumps(command[5:]).encode()
        for method in (self.command.encode_many, self.command.decode_many):
            with patch.object(self.command, '_run', side_effect=run) as process:
                paths = [f'folder/{i}' for i in range(300)] + ['folder/0']
                self.assertEqual(method(paths), paths)
                self.assertEqual(process.call_count, 3 if os.name == 'nt' else 1)

    def test_windows_mapping_retains_small_command_batches(self):
        def run(arguments, path, **kwargs):
            command = arguments('view:')
            paths = command[5:]
            self.assertLessEqual(len(paths), 128)
            self.assertLessEqual(sum(2 * len(path.encode('utf-8')) + 64 for path in paths), 24 * 1024)
            return json.dumps(paths).encode()
        with patch('features.rclone.localcrypt.transport.os.name', 'nt'), patch.object(
                self.command, '_run', side_effect=run) as process:
            paths = [f'folder/{i}' for i in range(300)]
            self.assertEqual(self.command.decode_many(paths), paths)
            self.assertEqual(process.call_count, 3)

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

    def test_batch_encoding_bounds_and_cancellation(self):
        with patch.object(session, 'revocation_check', return_value=lambda: False), \
                patch.object(session, 'launch') as launch:
            self.assertEqual(self.command.encode_many([]), [])
            with self.scope.scope(lambda: True), self.assertRaises(OperationCancelled):
                self.command.encode_many(['private.md'])
            launch.assert_not_called()
        with patch.object(self.command, '_run', return_value=b'["one"]'):
            with self.assertRaises(ValueError):
                self.command.encode_many(['one', 'two'])

    def test_encode_rejects_incomplete_or_ambiguous_results(self):
        with patch.object(session, 'revocation_check', return_value=lambda: False), \
             patch.object(session, 'launch', return_value=({}, 'view:', '')), \
             patch('features.rclone.localcrypt.transport.run_bytes') as run:
            for reply in (b'[]', b'["one","two"]', b'{}', b'[null]', b'[123]'):
                run.return_value = reply
                with self.assertRaisesRegex(ValueError, 'batch result'):
                    self.command.encode('private.md')
