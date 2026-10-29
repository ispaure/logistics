"""Bounded shared rewind ranges, concurrent fetches and credential revocation."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from io import BytesIO
from threading import Event, Thread
import unittest
from features.video.buffering import BufferingPolicy, MemoryRanges


class VideoMemoryTests(unittest.TestCase):
    def policy(self):
        return BufferingPolicy(memory_bytes=24, range_bytes=8, chunk_bytes=4)

    def test_rewind_uses_shared_ranges_and_lru_stays_bounded(self):
        cache = MemoryRanges(64, self.policy(), lambda: None)
        raw = bytes(range(64))
        calls = []
        class Stream(BytesIO):
            def read(self, count):
                calls.append(self.tell())
                return super().read(count)
        with Stream(raw) as first:
            self.assertEqual(cache.read(0, 8, first), raw[:8])
            cache.read(8, 8, first)
        # A decoder seek opens a different HTTP/provider stream.
        with Stream(raw) as second:
            self.assertEqual(cache.read(0, 8, second), raw[:8])
            self.assertEqual(calls, [0, 8])
            cache.read(16, 8, second)
            cache.read(24, 8, second)
            self.assertEqual(cache.bytes, 24)
            self.assertNotIn(8, cache.blocks)
            self.assertIn(0, cache.blocks)
            cache.read(8, 8, second)
            self.assertEqual(calls[-1], 8)
            self.assertLessEqual(cache.bytes, 24)
        cache.close()
        self.assertEqual(cache.bytes, 0)
        self.assertFalse(cache.blocks)

    def test_cached_bytes_still_require_access_and_close_is_final(self):
        revoked = Event()
        def check():
            if revoked.is_set():
                raise PermissionError('Locked')
        cache = MemoryRanges(8, self.policy(), check)
        stream = BytesIO(b'12345678')
        cache.read(0, 8, stream)
        revoked.set()
        with self.assertRaises(PermissionError):
            cache.read(0, 8, stream)
        cache.close()
        revoked.clear()
        with self.assertRaises(PermissionError):
            cache.read(0, 8, stream)

    def test_parallel_streams_share_one_fetch(self):
        entered, release = Event(), Event()
        cache = MemoryRanges(8, self.policy(), lambda: None)
        results, calls = [], []
        class Stream(BytesIO):
            def read(self, count):
                calls.append(count)
                entered.set()
                if not release.wait(2):
                    raise OSError('Test source timed out')
                return super().read(count)
        def read():
            with Stream(b'12345678') as stream:
                results.append(cache.read(0, 8, stream))
        workers = [Thread(target=read), Thread(target=read)]
        try:
            workers[0].start()
            self.assertTrue(entered.wait(2))
            workers[1].start()
            release.set()
            for worker in workers:
                worker.join(3)
            self.assertEqual(results, [b'12345678', b'12345678'])
            self.assertEqual(calls, [8])
        finally:
            release.set()
            for worker in workers:
                if worker.ident is not None:
                    worker.join(3)
            cache.close()

    def test_incomplete_range_does_not_poison_cache(self):
        cache = MemoryRanges(8, self.policy(), lambda: None)
        with self.assertRaises(OSError):
            cache.read(0, 8, BytesIO(b'short'))
        self.assertFalse(cache.blocks)
        self.assertFalse(cache.inflight)
        self.assertEqual(cache.read(0, 8, BytesIO(b'12345678')), b'12345678')
        cache.close()
