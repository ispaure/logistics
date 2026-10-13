"""Portable protected-key lifecycle tests; native gates exercise actual OS stores."""
import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from logisticsmobile.credential_vault import ProtectedVault, VaultUnavailable


class FixtureKeys:
    def __init__(self):
        self.keys = {}
        self.created = 0

    def create(self, identity, key):
        self.created += 1
        self.keys[identity] = key
        return {}  # Key remains in the fake OS store, never in filesystem metadata.

    def load(self, identity, record):
        if identity not in self.keys:
            raise VaultUnavailable('Missing fixture key')
        return self.keys[identity]

    def delete(self, identity):
        self.keys.pop(identity, None)


class MobileVaultTests(unittest.TestCase):
    def test_mobile_vault_key_is_device_owned_and_restored_without_password(self):
        with TemporaryDirectory() as directory:
            keys = FixtureKeys()
            vault = ProtectedVault(Path(directory).resolve() / 'Credentials', keys, 'fixture')
            self.assertIsNone(vault.unlock())
            values = vault.unlock(create=True)
            key = base64.b64decode(values['key'])
            self.assertNotIn(key, vault.record.read_bytes())
            self.assertNotIn(values['key'], vault.record.read_text())
            self.assertEqual(ProtectedVault(vault.root, keys, 'fixture').unlock(), values)
            self.assertEqual(keys.created, 1)
            vault.ciphertext.write_bytes(b'synthetic ciphertext')
            keys.keys.clear()
            with self.assertRaises(VaultUnavailable):
                vault.unlock(create=True)
            self.assertEqual(keys.created, 1)
            self.assertEqual(vault.ciphertext.read_bytes(), b'synthetic ciphertext')
            vault.forget()
            self.assertIsNone(vault.unlock())

    def test_mobile_vault_missing_corrupt_linked_metadata_never_replaces_keys(self):
        with TemporaryDirectory() as directory:
            keys = FixtureKeys()
            root = Path(directory).resolve()
            vault = ProtectedVault(root / 'Credentials', keys, 'fixture')
            vault.ciphertext.write_bytes(b'preserve')
            with self.assertRaises(VaultUnavailable):
                vault.unlock(create=True)
            self.assertEqual(keys.created, 0)
            vault.forget()
            vault.record.write_text(json.dumps({'id': '../escape', 'schema': 1, 'platform': 'fixture'}))
            with self.assertRaises(VaultUnavailable):
                vault.unlock(create=True)
            vault.forget()
            target = root / 'external'
            target.write_text('external data')
            vault.record.symlink_to(target)
            with self.assertRaises(OSError):
                vault.unlock(create=True)
            vault.forget()
            self.assertEqual(target.read_text(), 'external data')
            self.assertEqual(keys.created, 0)
