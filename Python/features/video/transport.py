"""Revocable loopback range transport. No plaintext staging or directory serving."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from commonUtils.runtime.operations import OperationCancelled
from secrets import token_urlsafe
from threading import Event, Thread, BoundedSemaphore


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


class VideoTransport:
    """Expose only explicitly admitted resources under unguessable URLs.

    The transport stays on loopback even during renderer playback: VLC owns
    the receiver transport. Neither credentials nor storage paths reach VLC.
    """
    def __init__(self, content):
        self.content = content
        self.closed = Event()
        self.paused = Event()
        self.slots = BoundedSemaphore(4)
        self.route = '/' + token_urlsafe(32) + '/video' + content.path[content.path.rfind('.'):].lower()
        self.resources = {self.route: content}
        transport = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass  # Capability URLs and private names must never enter logs.

            def do_HEAD(self):
                self.serve(False)

            def do_GET(self):
                self.serve(True)

            def serve(self, body):
                self.connection.settimeout(10)
                resource = transport.resources.get(self.path)
                if resource is None:
                    self.send_error(404)
                    return
                if not transport.slots.acquire(blocking=False):
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
                        mime = 'video/mp4' if resource.path.lower().endswith('.mp4') else 'video/x-matroska'
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
                        while remaining:
                            transport.check(resource)
                            data = stream.read(min(256 * 1024, remaining))
                            transport.check(resource)
                            if not data:
                                raise OSError('Incomplete video range.')
                            self.wfile.write(data)
                            remaining -= len(data)
                except (OSError, ValueError, PermissionError, OperationCancelled):
                    self.close_connection = True
                finally:
                    transport.slots.release()

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = Thread(target=self.server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return f'http://127.0.0.1:{self.server.server_port}{self.route}'

    def check(self, resource=None):
        if self.closed.is_set() or self.paused.is_set():
            raise PermissionError('Video transport is suspended.')
        self.content.check()
        if resource is not None:
            resource.check()

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
