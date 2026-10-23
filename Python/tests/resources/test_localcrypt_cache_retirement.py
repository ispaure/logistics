"""Late LocalCrypt workers cannot repopulate retired private caches."""
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from commonUtils.runtime.resources.lifetime import WorkerCancellation
from features.rclone import session
from features.rclone.localcrypt import backend, transport
from features.rclone.localcrypt.read_cache import PrivateReadCache
from features.rclone.localcrypt.transport import CryptCommand


class LocalCryptCacheRetirementTests(unittest.TestCase):
    def provider(self, root):
        provider = backend.CryptResources.__new__(backend.CryptResources)
        provider.root, provider.binary = root, Path('synthetic-rclone')
        provider.context = root / 'fixture.session'
        provider._cancellation = WorkerCancellation()
        provider._cache = PrivateReadCache(root, provider._check_active)
        provider._commands = CryptCommand(provider.binary, provider.context, provider._cancellation,
                                          provider._check_active, closed=lambda: provider.closed)
        session.remember(provider.context, {'view': {'type': 'local'}})
        self.addCleanup(provider.close)
        return provider

    def assert_empty(self, provider):
        for name in ('_paths', '_directories', '_sizes', '_blocks'):
            self.assertEqual(getattr(provider._cache, name), {}, name)
        self.assertEqual(provider._cache._bytes, 0)

    def test_late_path_encoding_or_listing_cannot_restore_names_after_close(self):
        for operation in ('encode', 'list', 'search'):
            with self.subTest(operation=operation), TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'ciphertext-folder').mkdir()
                provider = self.provider(root)
                guarded, resume = threading.Event(), threading.Event()
                results, failures = [], []
                original_guard = backend.guard_ciphertext_path
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
                with patch.object(backend, 'guard_ciphertext_path', side_effect=guard), \
                     patch.object(transport, 'run_bytes', return_value=b'["ciphertext-folder"]'), \
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
                provider._cache.remember_size('private-file', ('revision',), 42)
            self.assert_empty(provider)

    def test_close_discards_plaintext_before_notifying_other_observers(self):
        with TemporaryDirectory() as directory:
            provider = self.provider(Path(directory))
            provider._cache.remember_block(('private-file', ('revision',), 0, 23), b'synthetic-private-bytes')
            class Observer:
                def close(_self):
                    self.assert_empty(provider)
            observer = Observer()
            session.on_forget(provider.context, observer.close)
            provider.close()


class PrivateReadCacheTests(unittest.TestCase):
    def test_path_budget_releases_directory_names_and_keeps_recent_mappings(self):
        root = Path('/synthetic')
        cache = PrivateReadCache(root, lambda: None, max_paths=2)
        cache.remember_path('folder', root / 'cipher-folder', directory=True)
        cache.remember_path('file', root / 'cipher-file')
        self.assertEqual(cache.path('folder', directory=True), root / 'cipher-folder')
        cache.remember_path('third', root / 'cipher-third', directory=True)
        self.assertIsNone(cache.path('file'))
        cache.remember_path('fourth', root / 'cipher-fourth')
        self.assertIsNone(cache.path('folder', directory=True))
        self.assertEqual(cache.path('third', directory=True), root / 'cipher-third')
        self.assertEqual(cache.path('', directory=True), root)

    def test_block_limits_evict_least_recently_read_bytes(self):
        cache = PrivateReadCache(Path('/synthetic'), lambda: None, max_bytes=6, max_blocks=2)
        keys = [(name, ('revision',), 0, 3) for name in ('one', 'two', 'three')]
        cache.remember_block(keys[0], b'one')
        cache.remember_block(keys[1], b'two')
        self.assertEqual(cache.block(keys[0]), b'one')
        cache.remember_block(keys[2], b'big')
        self.assertIsNone(cache.block(keys[1]))
        self.assertEqual(cache.block(keys[0]), b'one')
        cache.remember_block(('oversize', (), 0, 7), b'1234567')
        self.assertEqual(cache._bytes, 0)
        self.assertEqual(cache._blocks, {})

    def test_zero_size_and_empty_block_are_hits_but_other_revisions_miss(self):
        cache = PrivateReadCache(Path('/synthetic'), lambda: None, max_sizes=1)
        cache.remember_size('empty', ('first',), 0)
        self.assertEqual(cache.size('empty', ('first',)), 0)
        self.assertIsNone(cache.size('empty', ('changed',)))
        cache.remember_size('next', ('next',), 3)
        self.assertIsNone(cache.size('empty', ('first',)))
        key = 'empty', ('first',), 0, 1
        cache.remember_block(key, b'')
        self.assertEqual(cache.block(key), b'')

    def test_forget_staging_path_releases_its_metadata_and_verified_plaintext(self):
        cache = PrivateReadCache(Path('/synthetic'), lambda: None)
        for name in ('original.md', '.save-token.md'):
            cache.remember_path(name, Path('/synthetic') / name)
            cache.remember_size(name, ('revision',), 3)
            cache.remember_block((name, ('revision',), 0, 3), b'abc')
        cache.forget_path('.save-token.md')
        self.assertIsNone(cache.path('.save-token.md'))
        self.assertIsNone(cache.size('.save-token.md', ('revision',)))
        self.assertIsNone(cache.block(('.save-token.md', ('revision',), 0, 3)))
        self.assertEqual(cache.block(('original.md', ('revision',), 0, 3)), b'abc')
        self.assertEqual(cache._bytes, 3)

    def test_retired_cache_refuses_reads_and_late_bytes_without_validating_again(self):
        from unittest.mock import Mock
        validate = Mock()
        cache = PrivateReadCache(Path('/synthetic'), validate)
        key = 'private', ('revision',), 0, 3
        cache.remember_block(key, b'abc')
        self.assertTrue(cache.retire())
        self.assertFalse(cache.retire())
        validate.reset_mock()
        for action in (lambda: cache.block(key), lambda: cache.remember_block(key, b'late'),
                       lambda: cache.path('private'), lambda: cache.size('private', ())):
            with self.assertRaises(ValueError):
                action()
        validate.assert_not_called()
        self.assertEqual(cache._bytes, 0)
        self.assertEqual(cache._blocks, {})

    def test_revoked_access_cannot_read_already_cached_bytes(self):
        active = True
        def validate():
            if not active:
                raise ValueError('revoked')
        cache = PrivateReadCache(Path('/synthetic'), validate)
        key = 'private', ('revision',), 0, 3
        cache.remember_block(key, b'abc')
        active = False
        with self.assertRaisesRegex(ValueError, 'revoked'):
            cache.block(key)
