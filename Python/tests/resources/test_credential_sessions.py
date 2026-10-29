"""Registry instances own independent, revocable in-memory credential trees."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
import unittest
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

class CredentialRevocationFailureTests(unittest.TestCase):
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
