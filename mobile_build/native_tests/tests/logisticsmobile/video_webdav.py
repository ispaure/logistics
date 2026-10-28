"""Read-only loopback WebDAV over synthetic video fixtures for native probes."""
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import quote, unquote, urlsplit
from xml.etree.ElementTree import Element, SubElement, tostring


class VideoWebDAV:
    def __init__(self, root):
        import ssl
        root = Path(root)
        self.root = (root / 'remote').resolve()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(root / 'tls/server.pem'), str(root / 'tls/server.key'))
        self.metrics = dict(propfind=0, get=0, ranges=0, bytes=0, encrypted_ranges=0)
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def path_for_request(self):
                key = unquote(urlsplit(self.path).path).lstrip('/')
                path = (fixture.root / key).resolve()
                if path != fixture.root and fixture.root not in path.parents:
                    raise ValueError('Invalid fixture path')
                return path

            def do_PROPFIND(self):
                fixture.metrics['propfind'] += 1
                length = int(self.headers.get('Content-Length', 0))
                if length:
                    self.rfile.read(length)
                try:
                    path = self.path_for_request()
                    if not path.exists():
                        self.send_error(404)
                        return
                    rows = [path]
                    if path.is_dir() and self.headers.get('Depth') != '0':
                        rows.extend(sorted(path.iterdir()))
                    document = Element('{DAV:}multistatus')
                    for row in rows:
                        response = SubElement(document, '{DAV:}response')
                        key = row.relative_to(fixture.root).as_posix()
                        href = '/' + ('' if key == '.' else quote(key))
                        if row.is_dir() and not href.endswith('/'):
                            href += '/'
                        SubElement(response, '{DAV:}href').text = href
                        propstat = SubElement(response, '{DAV:}propstat')
                        prop = SubElement(propstat, '{DAV:}prop')
                        kind = SubElement(prop, '{DAV:}resourcetype')
                        if row.is_dir():
                            SubElement(kind, '{DAV:}collection')
                        stat = row.stat()
                        SubElement(prop, '{DAV:}getcontentlength').text = str(0 if row.is_dir() else stat.st_size)
                        SubElement(prop, '{DAV:}getlastmodified').text = formatdate(stat.st_mtime, usegmt=True)
                        SubElement(prop, '{DAV:}getetag').text = f'"{stat.st_size}-{stat.st_mtime_ns}"'
                        SubElement(propstat, '{DAV:}status').text = 'HTTP/1.1 200 OK'
                    data = tostring(document, encoding='utf-8', xml_declaration=True)
                    self.send_response(207)
                    self.send_header('Content-Type', 'application/xml; charset=utf-8')
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except (OSError, ValueError):
                    self.send_error(404)

            def do_HEAD(self):
                self.serve(False)

            def do_GET(self):
                self.serve(True)

            def serve(self, body):
                from features.video.transport import byte_range
                try:
                    path = self.path_for_request()
                    if not path.is_file():
                        self.send_error(404)
                        return
                    size = path.stat().st_size
                    header = self.headers.get('Range')
                    start, end = byte_range(header, size)
                    self.send_response(206 if header else 200)
                    self.send_header('Content-Length', str(end - start + 1))
                    self.send_header('Content-Type', 'application/octet-stream')
                    self.send_header('Accept-Ranges', 'bytes')
                    self.send_header('Last-Modified', formatdate(path.stat().st_mtime, usegmt=True))
                    if header:
                        self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
                    self.end_headers()
                    if body:
                        fixture.metrics['get'] += 1
                        fixture.metrics['ranges'] += bool(header)
                        fixture.metrics['encrypted_ranges'] += bool(header and '/encrypted/' in self.path)
                        with path.open('rb') as stream:
                            stream.seek(start)
                            left = end - start + 1
                            while left:
                                data = stream.read(min(left, 256 * 1024))
                                if not data:
                                    break
                                self.wfile.write(data)
                                fixture.metrics['bytes'] += len(data)
                                left -= len(data)
                except (OSError, ValueError):
                    self.close_connection = True

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.server.daemon_threads = True
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return f'https://127.0.0.1:{self.server.server_port}/'

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
