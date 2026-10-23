"""Registry instances own independent, revocable in-memory credential trees."""
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
        self.assertEqual(first.package_path(root), Path('/synthetic/account.zip'))
        self.assertEqual(second.names(root), ['Other'])

    def test_returned_credentials_are_detached_from_registry(self):
        registry = CredentialSessions()
        path = Path('/synthetic/account.session')
        registry.remember(path, {'Fixture': {'type': 'local'}})
        snapshot = registry.credentials(path)
        snapshot['Fixture']['type'] = 'changed'
        self.assertEqual(registry.credentials(path)['Fixture']['type'], 'local')


if __name__ == '__main__':
    unittest.main()
