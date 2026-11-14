"""Session-scoped HLS access to the iOS Matroska stream-copy adapter."""
from http.server import BaseHTTPRequestHandler
from re import fullmatch
from secrets import token_urlsafe
from threading import BoundedSemaphore, Event, Lock, Thread

from features.video.transport import VideoHTTPServer, byte_range


class MKVStream:
    def __init__(self, owner, path, cancelled):
        from rubicon.objc import ObjCClass, py_from_ns
        from rubicon.objc.runtime import autoreleasepool
        self.owner = owner
        self.cancelled = cancelled
        self.stopped = Event()
        self.lock = Lock()
        self.slots = BoundedSemaphore(4)
        self.route = '/' + token_urlsafe(32) + '/'
        self.cached = None
        with autoreleasepool():
            remux = ObjCClass('LGMKVRemux')
            address = remux.streamAddress()
            if address is None:
                raise ValueError('Native MKV playback requires Wi-Fi.')
            self.remux = remux.alloc().initWithPath(str(path))
            if self.remux is None or not self.allowed():
                raise ValueError('This MKV cannot be streamed.')
            init = self.remux.initialization
            if init is None:
                raise ValueError('The MKV does not begin at a supported keyframe.')
            self.init = py_from_ns(init)
            self.playlist = str(self.remux.playlist).encode('ascii')
        stream = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(6)

            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_media(body=True)

            def do_HEAD(self):
                self.send_media(body=False)

            def send_media(self, *, body):
                if not self.path.startswith(stream.route) or not stream.allowed():
                    self.send_error(404)
                    return
                if not stream.slots.acquire(blocking=False):
                    self.send_error(503)
                    return
                try:
                    data, mime = stream.resource(self.path[len(stream.route):])
                    if data is None or not stream.allowed():
                        self.send_error(404)
                        return
                    requested = self.headers.get('Range')
                    try:
                        first, last = byte_range(requested, len(data))
                    except (ValueError, OverflowError):
                        self.send_response(416)
                        self.send_header('Content-Range', f'bytes */{len(data)}')
                        self.send_header('Content-Length', '0')
                        self.end_headers()
                        return
                    self.send_response(206 if requested else 200)
                    self.send_header('Content-Type', mime)
                    self.send_header('Content-Length', str(last - first + 1))
                    self.send_header('Accept-Ranges', 'bytes')
                    self.send_header('Cache-Control', 'no-store')
                    if requested:
                        self.send_header('Content-Range', f'bytes {first}-{last}/{len(data)}')
                    self.end_headers()
                    if body:
                        view = memoryview(data)
                        for offset in range(first, last + 1, 256 * 1024):
                            if not stream.allowed():
                                break
                            self.wfile.write(view[offset:min(last + 1, offset + 256 * 1024)])
                except (OSError, ValueError):
                    self.close_connection = True
                finally:
                    stream.slots.release()

        self.server = VideoHTTPServer((str(address), 0), Handler)
        self.server.daemon_threads = False
        self.thread = Thread(target=self.server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
        try:
            self.thread.start()
        except BaseException:
            self.server.server_close()
            raise
        self.url = f'http://{address}:{self.server.server_port}{self.route}video.m3u8'

    def allowed(self):
        if self.stopped.is_set() or self.cancelled.is_set() or not self.owner.allowed(external=True):
            return False
        try:
            self.owner.content.check()
        except (OSError, ValueError):
            return False
        return True

    def resource(self, name):
        if name == 'video.m3u8':
            return self.playlist, 'application/vnd.apple.mpegurl'
        if name == 'init.mp4':
            return self.init, 'video/mp4'
        match = fullmatch(r'segment-([0-9]{1,5})\.m4s', name)
        if match is None:
            return None, None
        index = int(match[1])
        from rubicon.objc import py_from_ns
        from rubicon.objc.runtime import autoreleasepool
        with self.lock, autoreleasepool():
            if not self.allowed():
                return None, None
            if self.cached is None or self.cached[0] != index:
                media = self.remux.segment(index)
                if media is None or not self.allowed():
                    return None, None
                self.cached = index, py_from_ns(media)
            return self.cached[1], 'video/iso.segment'

    def close(self):
        self.stopped.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.remux = None
        self.cached = None
