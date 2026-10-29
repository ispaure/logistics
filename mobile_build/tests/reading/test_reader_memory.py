"""Cross-runtime admission policy and memory-only accounting."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.EXTENDED
from pathlib import Path
from types import SimpleNamespace
import unittest
from mobile.reader_memory import (private_buffer_bytes, NATIVE_ARCHIVE_POOL,
                                          PRIVATE_BUFFERS, MANAGED_RESERVE, MIB, trim_content_cache)


class ReaderMemoryTests(unittest.TestCase):
    def test_content_factory_buffers_are_counted_and_trimmed_through_wrapper(self):
        backend = SimpleNamespace(data=b'decoded fixture', cache={'member': b'cached member'}, cache_bytes=13)
        source = SimpleNamespace(backend=backend)
        owner = SimpleNamespace(crypt_reader=SimpleNamespace(source=source))
        self.assertEqual(private_buffer_bytes([owner]), len(backend.data) + len(backend.cache['member']))
        trim_content_cache(source)
        self.assertEqual(backend.cache_bytes, 0)
        self.assertEqual(private_buffer_bytes([owner]), len(backend.data))

    def test_native_pool_matches_python_reserve_without_lowering_per_archive_limit(self):
        source = (Path(__file__).resolve().parents[2] / 'rclone_bridge/remote_cache.go').read_text()
        self.assertIn('const remoteComicPoolLimit int64 = 128 * 1024 * 1024', source)
        self.assertIn('const remoteComicLimit int64 = 128 * 1024 * 1024', source)
        self.assertEqual(NATIVE_ARCHIVE_POOL, 128 * MIB)
        self.assertEqual(PRIVATE_BUFFERS, 32 * MIB)
        self.assertEqual(MANAGED_RESERVE, 384 * MIB)

    def test_shared_bytes_count_once_but_member_cache_and_edits_are_included(self):
        data = b'private content sentinel'
        cached = b'member sentinel'
        text = 'unsaved sentinel 😀'
        source = SimpleNamespace(data=data, cache={'page': cached})
        reader = SimpleNamespace(data=data, source=source, text=text)
        owner = SimpleNamespace(crypt_reader=reader, crypt_text=SimpleNamespace(value=text))
        self.assertEqual(private_buffer_bytes([owner, owner]), len(data)+len(cached)+4*len(text))
        source.cache.clear()
        self.assertEqual(private_buffer_bytes([owner]), len(data)+4*len(text))
