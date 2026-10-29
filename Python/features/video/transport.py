"""Revocable loopback range transport. No plaintext staging or directory serving."""
from contextlib import contextmanager
from queue import Queue, Empty, Full
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from commonUtils.runtime.operations import OperationCancelled
from secrets import token_urlsafe
from threading import Event, Thread, BoundedSemaphore
from time import monotonic
from .buffering import DEFAULT_BUFFERING


def byte_range(value, size):
    if value is None:
        return 0, size - 1
    if not value.startswith('bytes=') or ',' in value:
        raise ValueError('One byte range is required.')
    left, separator, right = value[6:].partition('-')
    if not separator or (not left and not right):
        raise ValueError('Invalid byte range.')
    if left and (not left.isascii() or not left.isdecimal()):
        raise ValueError('Invalid range start.')
    if right and (not right.isascii() or not right.isdecimal()):
        raise ValueError('Invalid range end.')
    if not left:
        count = int(right)
        if count <= 0:
            raise ValueError('Invalid suffix range.')
        return max(0, size - count), size - 1
    start, end = int(left), min(int(right), size - 1) if right else size - 1
    if start > end or start >= size:
        raise ValueError('Unsatisfiable byte range.')
    return start, end


@contextmanager
def read_ahead(stream, remaining, check, *, waiting=lambda active: None, stall_after=None, policy=DEFAULT_BUFFERING):
    """Overlap remote fetches with decoder reads using a bounded queue.

    The caller keeps the stream alive until the producer has stopped. Queued
    plaintext remains memory-only and is checked again before publication.
    """
    stall_after = policy.stall_seconds if stall_after is None else stall_after
    pending, stopped, starved = Queue(maxsize=policy.read_ahead_chunks), Event(), Event()

    def set_waiting(active):
        if active != starved.is_set():
            starved.set() if active else starved.clear()
            waiting(active)

    def publish(value):
        while not stopped.is_set():
            try:
                pending.put(value, timeout=.05)
                return True
            except Full:
                pass
        return False

    def produce():
        left = remaining
        try:
            while left and not stopped.is_set():
                check()
                data = stream.read(min(policy.chunk_bytes, left))
                check()
                if not data:
                    raise OSError('Incomplete video range.')
                left -= len(data)
                if not publish(data):
                    return
            publish(None)
        except Exception as error:
            publish(error)

    def consume():
        idle_since = monotonic()
        while True:
            check()
            try:
                value = pending.get(timeout=.05)
            except Empty:
                if monotonic() - idle_since >= stall_after:
                    set_waiting(True)
                continue
            check()
            set_waiting(False)
            idle_since = monotonic()
            if value is None:
                return
            if isinstance(value, Exception):
                raise value
            yield value

    worker = Thread(target=produce, name='video-read-ahead', daemon=True)
    worker.start()
    try:
        yield consume()
    finally:
        stopped.set()
        set_waiting(False)
        worker.join()  # Never close a provider while its reader is still using it.
        while not pending.empty():
            pending.get_nowait()


class VideoTransport:
    """Expose only explicitly admitted resources under unguessable URLs.

    The transport stays on loopback even during renderer playback: VLC owns
    the receiver transport. Neither credentials nor storage paths reach VLC.
    """
    def __init__(self, content, *, waiting=lambda token, active: None, failed=lambda category: None):
        self.content = content
        self.waiting, self.failed = waiting, failed
        self.closed = Event()
        self.paused = Event()
        self.slots = BoundedSemaphore(4)
        self.route = '/' + token_urlsafe(32) + '/video' + content.path[content.path.rfind('.'):].lower()
        self.resources = {self.route: content}
        transport = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def setup(self):
                super().setup()
                self.connection.settimeout(10)

            def log_message(self, *args):
                pass  # Capability URLs and private names must never enter logs.

            def do_HEAD(self):
                self.serve(False)

            def do_GET(self):
                self.serve(True)

            def serve(self, body):
                resource = transport.resources.get(self.path)
                if resource is None:
                    self.send_error(404)
                    return
                # AVI demuxers open replacement ranges before old requests have
                # finished unwinding their read-ahead workers. Queue that burst
                # instead of turning ordinary seeks into a playback-ending 503.
                deadline = monotonic() + 10
                while not transport.slots.acquire(timeout=.05):
                    if transport.closed.is_set() or transport.paused.is_set():
                        self.send_error(403)
                        return
                    if monotonic() >= deadline:
                        if resource is transport.content:
                            transport.failed('busy')
                        self.send_error(503)
                        return
                try:
                    transport.check(resource)
                    value = self.headers.get('Range')
                    try:
                        start, end = byte_range(value, resource.size)
                    except (ValueError, OverflowError):
                        self.send_response(416)
                        self.send_header('Content-Range', f'bytes */{resource.size}')
                        self.send_header('Content-Length', '0')
                        self.end_headers()
                        return
                    # Open and seek before sending success. Credential failures
                    # must never turn into a successful response with zero bytes.
                    with resource.open() as stream:
                        stream.seek(start)
                        self.send_response(206 if value is not None else 200)
                        from mimetypes import guess_type
                        mime = guess_type(resource.path)[0] or 'application/octet-stream'
                        self.send_header('Content-Type', mime if resource is transport.content else 'application/octet-stream')
                        self.send_header('Content-Length', str(end - start + 1))
                        self.send_header('Accept-Ranges', 'bytes')
                        self.send_header('Cache-Control', 'no-store')
                        self.send_header('Connection', 'close')
                        if value is not None:
                            self.send_header('Content-Range', f'bytes {start}-{end}/{resource.size}')
                        self.end_headers()
                        self.close_connection = True
                        if not body:
                            return
                        remaining = end - start + 1
                        if getattr(resource, 'remote', False):
                            token = object()
                            notify = (lambda active: transport.waiting(token, active)) if resource is transport.content else (lambda active: None)
                            with read_ahead(stream, remaining,
                                    lambda: transport.check(resource, metadata=False), waiting=notify,
                                    policy=getattr(resource, 'buffering', DEFAULT_BUFFERING)) as chunks:
                                for data in chunks:
                                    transport.check(resource, metadata=False)
                                    self.wfile.write(data)
                            return
                        while remaining:
                            transport.check(resource, metadata=False)
                            data = stream.read(min(256 * 1024, remaining))
                            transport.check(resource, metadata=False)
                            if not data:
                                raise OSError('Incomplete video range.')
                            self.wfile.write(data)
                            remaining -= len(data)
                except (BrokenPipeError, ConnectionResetError, TimeoutError, OperationCancelled):
                    self.close_connection = True
                except (OSError, ValueError, PermissionError) as error:
                    if resource is transport.content:
                        transport.failed('access' if isinstance(error, PermissionError) else
                                         'changed' if isinstance(error, ValueError) else 'read')
                    self.close_connection = True
                finally:
                    transport.slots.release()

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        # server_close joins handlers and their read-ahead workers before the
        # presentation owner releases the retained provider and privacy scope.
        self.server.daemon_threads = False
        self.thread = Thread(target=self.server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return f'http://127.0.0.1:{self.server.server_port}{self.route}'

    def check(self, resource=None, *, metadata=True):
        if self.closed.is_set() or self.paused.is_set():
            raise PermissionError('Video transport is suspended.')
        # Revision validation belongs at range admission/open, and the provider
        # validates each remote range. Per-chunk metadata requests serialize
        # cloud RTTs ahead of every 256 KiB write and can starve the decoder.
        self.content.check() if metadata or not getattr(self.content, 'remote', False) else self.content.check_access()
        if resource is not None and resource is not self.content:
            resource.check() if metadata or not getattr(resource, 'remote', False) else resource.check_access()

    def add_subtitle(self, resource):
        self.check(resource)
        route = '/' + token_urlsafe(32) + '/subtitle' + resource.path[resource.path.rfind('.'):].lower()
        self.resources[route] = resource
        return f'http://127.0.0.1:{self.server.server_port}{route}'

    def suspend(self):
        self.paused.set()

    def resume(self):
        self.content.check_access()
        self.paused.clear()

    def close(self):
        if not self.closed.is_set():
            self.closed.set()
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=1)
