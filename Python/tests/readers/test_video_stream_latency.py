"""Loopback chunks retain local revocation without cloud metadata round trips."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from contextlib import contextmanager
from http.client import HTTPConnection, IncompleteRead
from io import BytesIO
from urllib.parse import urlsplit
import unittest
from features.video.transport import VideoTransport


class VideoStreamLatencyTests(unittest.TestCase):
    def test_overlapping_seek_waits_for_a_range_slot(self):
        from threading import Event, Thread
        from urllib.request import urlopen
        entered, complete = Event(), Event()
        class Content:
            path, remote, size = 'movie.avi', False, 4
            def check(self): pass
            def check_access(self): pass
            @contextmanager
            def open(self): yield BytesIO(b'data')
        transport = VideoTransport(Content())
        failures, result = [], []
        transport.failed = failures.append
        for _ in range(4):
            self.assertTrue(transport.slots.acquire(False))
        def request():
            entered.set()
            try:
                with urlopen(transport.url, timeout=3) as response:
                    result.append((response.status, response.read()))
            finally:
                complete.set()
        worker = Thread(target=request)
        worker.start()
        try:
            self.assertTrue(entered.wait(1))
            self.assertFalse(complete.wait(.15), 'A normal seek burst was rejected')
            transport.slots.release()
            self.assertTrue(complete.wait(2))
            self.assertEqual(result, [(200,b'data')])
            self.assertEqual(failures, [])
        finally:
            for _ in range(3): transport.slots.release()
            worker.join(3)
            transport.close()

    def test_optional_subtitle_failure_does_not_poison_video_retry(self):
        from http.client import RemoteDisconnected
        class Content:
            path, remote, size, revoked = 'movie.avi', False, 4, False
            def check(self):
                if self.revoked: raise PermissionError('sensitive provider detail')
            def check_access(self): self.check()
            @contextmanager
            def open(self): yield BytesIO(b'data')
        class Subtitle(Content):
            path = 'captions.srt'
            def check(self):
                if self.revoked: raise OSError('sensitive subtitle detail')
        content, subtitle, failures = Content(), Subtitle(), []
        transport = VideoTransport(content, failed=failures.append)
        def request(url):
            parts = urlsplit(url)
            connection = HTTPConnection(parts.hostname,parts.port,timeout=3)
            try:
                connection.request('GET',parts.path)
                with self.assertRaises(RemoteDisconnected): connection.getresponse()
            finally: connection.close()
        try:
            url = transport.add_subtitle(subtitle)
            subtitle.revoked = True
            request(url)
            self.assertEqual(failures,[])
            content.revoked = True
            request(transport.url)
            self.assertEqual(failures,['access'])
        finally: transport.close()

    def test_metadata_is_admitted_once_not_twice_per_chunk(self):
        class Content:
            path = 'movie.avi'
            remote = True
            size = 2 * 1024 * 1024
            metadata = 0
            access = 0
            def check(self):
                self.metadata += 1
            def check_access(self):
                self.access += 1
            @contextmanager
            def open(self):
                yield BytesIO(b'x' * self.size)
        content = Content()
        transport = VideoTransport(content)
        try:
            url = urlsplit(transport.url)
            connection = HTTPConnection(url.hostname, url.port, timeout=5)
            try:
                connection.request('GET', url.path)
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(len(response.read()), content.size)
            finally:
                connection.close()
            self.assertEqual(content.metadata, 1)
            self.assertGreaterEqual(content.access, 8)
        finally:
            transport.close()

    def test_revocation_during_remote_read_never_publishes_that_chunk(self):
        class Content:
            path, remote, size, revoked = 'private.avi', True, 1024, False
            def check(self):
                self.check_access()
            def check_access(self):
                if self.revoked:
                    raise PermissionError('Session closed')
            @contextmanager
            def open(self):
                owner = self
                class Stream(BytesIO):
                    def read(self, count):
                        result = super().read(count)
                        owner.revoked = True
                        return result
                yield Stream(b'x' * self.size)
        transport = VideoTransport(Content())
        try:
            url = urlsplit(transport.url)
            connection = HTTPConnection(url.hostname, url.port, timeout=5)
            try:
                connection.request('GET', url.path)
                response = connection.getresponse()
                with self.assertRaises(IncompleteRead) as caught:
                    response.read()
                self.assertEqual(caught.exception.partial, b'')
            finally:
                connection.close()
        finally:
            transport.close()

    def test_transport_close_waits_for_inflight_remote_reader(self):
        from threading import Event, Thread
        entered, release, exited, finished = Event(), Event(), Event(), Event()
        class Content:
            path, remote, size = 'movie.avi', True, 1024
            def check(self): pass
            def check_access(self): pass
            @contextmanager
            def open(self):
                class Stream(BytesIO):
                    def read(self, count):
                        entered.set()
                        if not release.wait(3):
                            raise OSError('Test reader timed out')
                        return super().read(count)
                try:
                    yield Stream(b'x' * self.size)
                finally:
                    exited.set()
        transport = VideoTransport(Content())
        url = urlsplit(transport.url)
        connection = HTTPConnection(url.hostname, url.port, timeout=5)
        connection.request('GET', url.path)
        response = connection.getresponse()
        def close():
            transport.close()
            finished.set()
        closer = Thread(target=close)
        try:
            self.assertTrue(entered.wait(2))
            closer.start()
            self.assertFalse(finished.wait(.1), 'Closed provider while remote read was active')
            release.set()
            closer.join(3)
            self.assertTrue(finished.is_set())
            self.assertTrue(exited.is_set())
        finally:
            release.set()
            connection.close()
            if closer.ident is not None:
                closer.join(3)
            transport.close()

    def test_local_content_keeps_revision_validation_for_each_chunk(self):
        class Content:
            remote, checks = False, 0
            def check(self):
                self.checks += 1
            def check_access(self):
                raise AssertionError('Local revision check was skipped')
        # Exercise the exact chunk admission policy without opening a socket.
        transport = VideoTransport.__new__(VideoTransport)
        from threading import Event
        transport.closed, transport.paused = Event(), Event()
        transport.content = Content()
        transport.check(metadata=False)
        self.assertEqual(transport.content.checks, 1)


class VideoReadAheadTests(unittest.TestCase):
    def test_prefetch_is_bounded_and_stops_before_stream_closes(self):
        from threading import Event
        from features.video.transport import read_ahead
        full = Event()
        class Stream:
            reads = 0
            def read(self, count):
                self.reads += 1
                if self.reads == 5:
                    full.set()
                return bytes([self.reads]) * count
        stream = Stream()
        with read_ahead(stream, 20 * 1024 * 1024, lambda: None) as chunks:
            self.assertTrue(full.wait(2), 'Read-ahead never reached its bounded queue')
            self.assertEqual(stream.reads, 5)
            self.assertEqual(next(chunks), b'\x01' * (1024 * 1024))
        # Context exit joins the worker, even with a full queue and early exit.
        self.assertLessEqual(stream.reads, 6)

    def test_queued_plaintext_is_not_delivered_after_revocation(self):
        from threading import Event
        from features.video.transport import read_ahead
        queued, revoked = Event(), Event()
        class Stream(BytesIO):
            def read(self, count):
                value = super().read(count)
                queued.set()
                return value
        def check():
            if revoked.is_set():
                raise PermissionError('Credentials revoked')
        with read_ahead(Stream(b'x' * (2 * 1024 * 1024)), 2 * 1024 * 1024, check) as chunks:
            self.assertTrue(queued.wait(2))
            revoked.set()
            with self.assertRaises(PermissionError):
                next(chunks)

    def test_starvation_reports_hold_then_readiness_and_clears_on_close(self):
        from threading import Event, Thread
        from features.video.transport import read_ahead
        held, release = Event(), Event()
        changes = []
        class Stream:
            def read(self, count):
                if not release.wait(2):
                    raise OSError('Test source timed out')
                return b'x' * count
        def waiting(active):
            changes.append(active)
            if active:
                held.set()
        def refill():
            if held.wait(2):
                release.set()
        refill_thread = Thread(target=refill)
        refill_thread.start()
        try:
            with read_ahead(Stream(), 1024, lambda: None, waiting=waiting, stall_after=0) as chunks:
                self.assertEqual(next(chunks), b'x' * 1024)
            self.assertEqual(changes, [True, False])
        finally:
            release.set()
            refill_thread.join(3)

    def test_remote_failure_is_propagated_after_complete_chunks(self):
        from features.video.transport import read_ahead
        class Stream:
            reads = 0
            def read(self, count):
                self.reads += 1
                if self.reads > 1:
                    raise OSError('Remote unavailable')
                return b'x' * count
        with read_ahead(Stream(), 2 * 1024 * 1024, lambda: None) as chunks:
            self.assertEqual(len(next(chunks)), 1024 * 1024)
            with self.assertRaisesRegex(OSError, 'Remote unavailable'):
                next(chunks)
