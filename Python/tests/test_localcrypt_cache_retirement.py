"""Late LocalCrypt workers cannot repopulate retired private caches."""
from collections import OrderedDict
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from commonUtils.runtime.resources.lifetime import WorkerCancellation
from features.rclone import session
from features.rclone.localcrypt import backend


class LocalCryptCacheRetirementTests(unittest.TestCase):
    def provider(self, root):
        provider = backend.CryptResources.__new__(backend.CryptResources)
        provider.root, provider.binary = root, Path('synthetic-rclone')
        provider.context, provider.closed = root / 'fixture.session', False
        provider._cache_lock = threading.RLock()
        provider._cancellation = WorkerCancellation()
        provider._encoded_paths, provider._directories = {}, {'': root}
        provider._sizes, provider._blocks = OrderedDict(), OrderedDict()
        provider._cache_bytes = 0
        session.remember(provider.context, {'view': {'type': 'local'}})
        self.addCleanup(provider.close)
        return provider

    def assert_empty(self, provider):
        for name in ('_encoded_paths', '_directories', '_sizes', '_blocks'):
            self.assertEqual(getattr(provider, name), {}, name)
        self.assertEqual(provider._cache_bytes, 0)

    def test_late_path_encoding_or_listing_cannot_restore_names_after_close(self):
        for operation in ('encode', 'list', 'search'):
            with self.subTest(operation=operation), TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'ciphertext-folder').mkdir()
                provider = self.provider(root)
                guarded, resume = threading.Event(), threading.Event()
                results, failures = [], []
                original_guard = backend._guard_path
                def guard(path, boundary):
                    original_guard(path, boundary)
                    if path == root / 'ciphertext-folder':
                        guarded.set()
                        if not resume.wait(5):
                            raise RuntimeError('fixture worker was not resumed')
                rows = b'[{"Name":"private-folder","Path":"private-folder","EncryptedPath":"ciphertext-folder","IsDir":true,"Size":0}]'
                def read():
                    try:
                        if operation == 'encode':
                            results.append(provider.encrypted_path('private-folder'))
                        elif operation == 'list':
                            results.extend(provider.list())
                        else:
                            results.extend(provider.search_entries())
                    except Exception as error:
                        failures.append(error)
                with patch.object(backend, '_guard_path', side_effect=guard), \
                     patch.object(backend, 'run_bytes', return_value=b'["ciphertext-folder"]'), \
                     patch.object(provider, 'command', return_value=rows):
                    worker = threading.Thread(target=read)
                    worker.start()
                    try:
                        self.assertTrue(guarded.wait(5))
                        provider.close()
                    finally:
                        resume.set()
                        worker.join(timeout=5)
                    self.assertFalse(worker.is_alive())
                self.assert_empty(provider)
                self.assertEqual(results, [])
                self.assertEqual(len(failures), 1)
                self.assertIsInstance(failures[0], ValueError)

    def test_late_size_publication_is_rejected(self):
        with TemporaryDirectory() as directory:
            provider = self.provider(Path(directory))
            provider.close()
            with self.assertRaises(ValueError):
                provider._remember_size('private-file', ('revision',), 42)
            self.assert_empty(provider)

    def test_close_discards_plaintext_before_notifying_other_observers(self):
        with TemporaryDirectory() as directory:
            provider = self.provider(Path(directory))
            provider._blocks['block'] = b'synthetic-private-bytes'
            provider._cache_bytes = 23
            class Observer:
                def close(_self):
                    self.assert_empty(provider)
            observer = Observer()
            session.on_forget(provider.context, observer.close)
            provider.close()
