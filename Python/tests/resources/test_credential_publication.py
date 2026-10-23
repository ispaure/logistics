"""Credential publication keeps invalidation fail-safe across mobile scenes."""
import threading
import unittest
from unittest.mock import patch

from features.rclone.mobile.credential_state import NativeCredentialState
from features.rclone.localcrypt.backend import CryptResources


class CredentialPublicationTests(unittest.TestCase):
    def test_publication_notifies_all_scenes_after_observer_failure(self):
        state = NativeCredentialState()
        notified = []
        class Observer:
            def __init__(self, name):
                self.name = name
            def credentials_changed(self):
                notified.append(self.name)
                raise ValueError(self.name)
        first, second = Observer('first'), Observer('second')
        state.observers.add(first)
        state.document_observers.add(second)
        with self.assertRaisesRegex(ValueError, 'first'):
            state.publish('clear', {}, {'epoch': 1})
        self.assertEqual(notified, ['first', 'second'])
        self.assertEqual(state.generation, 1)
        self.assertEqual(state.package_records, ())
        state.publish('clear', {}, {'epoch': 1})
        self.assertEqual(notified, ['first', 'second'])

    def test_closed_localcrypt_discards_plaintext_even_if_notification_fails(self):
        provider = CryptResources.__new__(CryptResources)
        provider.closed, provider.context = False, '/synthetic/reader'
        provider._cache_lock = threading.RLock()
        provider._blocks = {'block': b'synthetic plaintext'}
        provider._sizes = {'file': 10}
        provider._encoded_paths = {'file': 'ciphertext'}
        provider._directories = {'': 'root'}
        provider._cache_bytes = 19
        with patch('features.rclone.session.forget', side_effect=ValueError('synthetic observer failure')):
            with self.assertRaisesRegex(ValueError, 'synthetic observer failure'):
                provider.close()
        self.assertTrue(provider.closed)
        self.assertEqual(provider._blocks, {})
        self.assertEqual(provider._sizes, {})
        self.assertEqual(provider._encoded_paths, {})
        self.assertEqual(provider._directories, {})
        self.assertEqual(provider._cache_bytes, 0)
        provider.close()
