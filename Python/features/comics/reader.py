"""Local browser reader with lazy archive pages and direction-aware navigation."""

import atexit
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import threading
import webbrowser

from .pages import ComicPages
from .archive_io import archive_unchanged

_sessions = []


class ReaderSession:
    def __init__(self, path):
        self.pages = ComicPages(path)
        self.token = secrets.token_urlsafe(24)
        template = Path(__file__).with_name('reader.html').read_text(encoding='utf-8')
        self.html = template.replace('{{TITLE}}', escape(self.pages.path.name)).replace(
            '{{COUNT}}', str(len(self.pages.pages))).replace('{{RTL}}', 'true' if self.pages.right_to_left else 'false').encode()
        session = self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.headers.get('Host') != f'127.0.0.1:{session.server.server_port}':
                    self.send_error(403)
                    return
                prefix = f'/{session.token}/'
                if self.path == prefix:
                    data, mime = session.html, 'text/html; charset=utf-8'
                elif self.path.startswith(prefix + 'page/'):
                    number = self.path[len(prefix + 'page/'):]
                    if not number.isdecimal():
                        self.send_error(404)
                        return
                    try:
                        data, mime = session.pages.read_page(int(number))
                    except IndexError:
                        self.send_error(404)
                        return
                    except Exception as error:
                        self.send_error(409, str(error))
                        return
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Content-Security-Policy', "default-src 'none'; img-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'")
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *args):
                pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/{self.token}/'

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def open_reader(path):
    path = Path(path).absolute()
    session = next((item for item in _sessions if item.pages.path == path), None)
    if session is not None and not archive_unchanged(path, session.pages.document.snapshot):
        session.close()
        _sessions.remove(session)
        session = None
    fresh = session is None
    if fresh:
        session = ReaderSession(path)
    try:
        if not webbrowser.open(session.url, new=1):
            raise RuntimeError('The browser could not be opened')
    except Exception:
        if fresh:
            session.close()
        raise
    if fresh:
        _sessions.append(session)
    return session


@atexit.register
def close_readers():
    for session in _sessions:
        session.close()
    _sessions.clear()
