"""Loopback-only synthetic LM server used by portable and native app checks."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Event, Thread


@contextmanager
def fixture_server(*, mode='reply'):
    started, release, requests = Event(), Event(), []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            requests.append(('GET', self.path, self.headers.get('Authorization')))
            if mode == 'redirect':
                self.send_response(302)
                self.send_header('Location', '/not-allowed')
                self.end_headers()
            else:
                data = json.dumps({'data': [{'id': 'fixture-model'}]}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(('POST', self.path, self.headers.get('Authorization'), data))
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            try:
                if mode == 'tools':
                    event = {'choices': [{'delta': {'tool_calls': [{'id': 'forbidden'}]}}]}
                else:
                    event = {'choices': [{'delta': {'content': 'Native fixture reply'}}]}
                self.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
                self.wfile.flush()
                started.set()
                if mode == 'pause':
                    release.wait(10)
                if mode != 'incomplete':
                    self.wfile.write(b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1', started, release, requests
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(3)
