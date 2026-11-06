"""Registry instances own independent, revocable in-memory credential trees."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
import unittest
from unittest.mock import patch
from features.rclone.credential_sessions import CredentialSessions


class CredentialSessionsTests(unittest.TestCase):
    def test_independent_hosts_and_child_generations(self):
        first, second = CredentialSessions(), CredentialSessions()
        root, child = Path('/synthetic/account.session'), Path('/synthetic/reader.session')
        values = {'Fixture': {'type': 'local'}}
        first.remember(root, values, package_path=Path('/synthetic/account.zip'))
        first.remember(child, values, parent=root, private=True)
        second.remember(root, {'Other': {'type': 'local'}})
        revoked = first.revocation_check(child)
        self.assertEqual(first.paths(), [root])
        self.assertFalse(revoked())
        first.remember(root, values)
        self.assertTrue(revoked())
        self.assertIsNone(first.credentials(child))
        self.assertIsNone(first.package_path(root))
        first.forget(root)
        self.assertEqual(first.package_path(root), Path('/synthetic/account.zip'))
        self.assertEqual(second.names(root), ['Other'])

    def test_returned_credentials_are_detached_from_registry(self):
        registry = CredentialSessions()
        path = Path('/synthetic/account.session')
        registry.remember(path, {'Fixture': {'type': 'local'}})
        snapshot = registry.credentials(path)
        snapshot['Fixture']['type'] = 'changed'
        self.assertEqual(registry.credentials(path)['Fixture']['type'], 'local')

    def test_remembered_credentials_are_detached_from_shared_input(self):
        first, second = CredentialSessions(), CredentialSessions()
        path = Path('/synthetic/account.session')
        values = {'Fixture': {'type': 'local'}}
        for registry in (first, second):
            registry.remember(path, values, state_password='synthetic-password',
                              state_identity='synthetic-identity')
        revoked = first.revocation_check(path), second.revocation_check(path)
        authority = first.state_authority(path)
        values['Fixture']['type'] = 'changed'
        values['Added'] = {'type': 'local'}
        for registry in (first, second):
            self.assertEqual(registry.names(path), ['Fixture'])
            self.assertEqual(registry.credentials(path), {'Fixture': {'type': 'local'}})
            self.assertEqual(registry.state_authority(path), authority)
            with patch.dict('os.environ', {}, clear=True):
                environment, source, destination = registry.launch(path, 'Fixture:a', 'Fixture:b')
            alias = source.partition(':')[0]
            self.assertEqual(destination, alias + ':b')
            self.assertEqual(environment, {f'RCLONE_CONFIG_{alias.upper()}_TYPE': 'local'})
        self.assertFalse(revoked[0]())
        self.assertFalse(revoked[1]())

        first.remember(path, values)
        values.clear()
        self.assertTrue(revoked[0]())
        self.assertFalse(revoked[1]())
        self.assertEqual(first.credentials(path), {
            'Fixture': {'type': 'changed'}, 'Added': {'type': 'local'},
        })
        self.assertEqual(second.credentials(path), {'Fixture': {'type': 'local'}})


class CredentialRevocationFailureTests(unittest.TestCase):
    def test_failed_input_snapshot_preserves_existing_generation_tree(self):
        registry = CredentialSessions()
        root, child = Path('/synthetic/root'), Path('/synthetic/child')
        package = Path('/synthetic/account.zip')
        registry.remember(root, {'Root': {'type': 'local'}}, package_path=package,
                          state_password='synthetic-password', state_identity='synthetic-identity')
        registry.remember(child, {'Child': {'type': 'local'}}, parent=root, private=True)
        root_revoked, child_revoked = registry.revocation_check(root), registry.revocation_check(child)
        authority = registry.state_authority(child)
        notified = []

        class Observer:
            def close(self):
                notified.append(True)

        class Uncopyable(dict):
            def __deepcopy__(self, memo):
                raise ValueError('synthetic snapshot failure')

        observer = Observer()
        registry.on_forget(child, observer.close)
        with self.assertRaisesRegex(ValueError, 'synthetic snapshot failure'):
            registry.remember(root, Uncopyable(Replacement={'type': 'local'}))
        self.assertEqual(notified, [])
        self.assertFalse(root_revoked())
        self.assertFalse(child_revoked())
        self.assertEqual(registry.credentials(root), {'Root': {'type': 'local'}})
        self.assertEqual(registry.credentials(child), {'Child': {'type': 'local'}})
        self.assertEqual(registry.paths(), [root])
        self.assertEqual(registry.package_path(root), package)
        self.assertEqual(registry.state_authority(child), authority)
        self.assertEqual(registry.state_credentials(child),
                         ('synthetic-identity', bytearray(b'synthetic-password')))
        registry.forget(root)
        self.assertEqual(notified, [True])
        self.assertTrue(child_revoked())

    def test_replacement_is_owned_and_active_before_retired_observers_run(self):
        registry = CredentialSessions()
        root, child = Path('/synthetic/root'), Path('/synthetic/child')
        registry.remember(root, {'Root': {'type': 'local'}})
        registry.remember(child, {'Child': {'type': 'local'}}, parent=root, private=True)
        root_revoked, child_revoked = registry.revocation_check(root), registry.revocation_check(child)
        values = {'Replacement': {'type': 'local'}}
        observed = []

        class Observer:
            def __init__(self, name, fail=False):
                self.name, self.fail = name, fail

            def close(self):
                # A retired owner may discard the caller's staging mapping.
                values.clear()
                observed.append((self.name, root_revoked(), child_revoked(),
                                 registry.credentials(root), registry.credentials(child)))
                if self.fail:
                    raise ValueError('synthetic cleanup failure')

        parent_observer, child_observer = Observer('root'), Observer('child', True)
        registry.on_forget(root, parent_observer.close)
        registry.on_forget(child, child_observer.close)
        package = Path('/synthetic/replacement.zip')
        with self.assertRaisesRegex(ValueError, 'synthetic cleanup failure'):
            registry.remember(root, values, package_path=package,
                              state_password='synthetic-password', state_identity='synthetic-identity')
        expected = {'Replacement': {'type': 'local'}}
        self.assertEqual(observed, [
            ('child', True, True, expected, None),
            ('root', True, True, expected, None),
        ])
        self.assertEqual(registry.credentials(root), expected)
        self.assertFalse(registry.revocation_check(root)())
        self.assertEqual(registry.paths(), [root])
        self.assertEqual(registry.package_path(root), package)
        self.assertEqual(registry.state_credentials(root),
                         ('synthetic-identity', bytearray(b'synthetic-password')))
        registry.forget(root)
        self.assertEqual(len(observed), 2)

    def test_cyclic_parent_rejected_without_changing_existing_generations(self):
        registry = CredentialSessions()
        root, child = Path('/synthetic/root'), Path('/synthetic/child')
        registry.remember(root, {'Root': {'type': 'local'}})
        registry.remember(child, {'Child': {'type': 'local'}}, parent=root)
        root_revoked, child_revoked = registry.revocation_check(root), registry.revocation_check(child)
        for parent in (root, child):
            with self.subTest(parent=parent), self.assertRaisesRegex(ValueError, 'descendants'):
                registry.remember(root, {}, parent=parent)
            self.assertFalse(root_revoked())
            self.assertFalse(child_revoked())
        registry.forget(root)
        self.assertTrue(child_revoked())

    def test_failing_observer_does_not_block_remaining_revocation(self):
        registry = CredentialSessions()
        path = Path('/synthetic/account')
        registry.remember(path, {'Fixture': {'type': 'local'}})
        notified = []
        class Observer:
            def __init__(self, name, fail=False):
                self.name, self.fail = name, fail
            def close(self):
                notified.append(self.name)
                if self.fail:
                    raise ValueError('synthetic cleanup failure')
        first, second = Observer('first', True), Observer('second')
        registry.on_forget(path, first.close)
        registry.on_forget(path, second.close)
        with self.assertRaisesRegex(ValueError, 'synthetic cleanup failure'):
            registry.forget(path)
        self.assertEqual(notified, ['first', 'second'])
        self.assertIsNone(registry.credentials(path))


if __name__ == '__main__':
    unittest.main()
