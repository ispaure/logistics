"""Bounded OpenAI-compatible HTTP/SSE; no redirects, tools or implicit requests."""
import http.client
import json
from queue import Queue, Empty, Full
import socket
from threading import Event, Lock, Thread
import time
from urllib.parse import quote, urlsplit

from features.lm.domain import base_url

MAX_REPLY = 256 * 1024


class ChatCancelled(Exception):
    pass


class ChatClient:
    def __init__(self, url, api_key=''):
        self.url = base_url(url)
        if (not isinstance(api_key, str) or len(api_key) > 4096
                or any(not 33 <= ord(c) <= 126 for c in api_key)):
            raise ValueError('API keys must be printable ASCII without spaces or control characters.')
        self.api_key = api_key
        self.cancelled = Event()
        self.lock = Lock()
        self.connection = None
        self.socket = None

    def cancel(self):
        self.cancelled.set()
        with self.lock:
            connection = self.connection
            sock = self.socket or (connection.sock if connection else None)
        if sock:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def check(self):
        if self.cancelled.is_set():
            raise ChatCancelled('Request cancelled.')

    def request(self, endpoint, payload=None):
        self.check()
        parts = urlsplit(self.url)
        factory = http.client.HTTPSConnection if parts.scheme == 'https' else http.client.HTTPConnection
        connection = factory(parts.hostname, parts.port, timeout=15)
        with self.lock:
            self.connection = connection
        headers = {'Accept': 'text/event-stream' if payload is not None else 'application/json'}
        if self.api_key:
            headers['Authorization'] = 'Bearer ' + self.api_key
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8') if payload is not None else None
        if body is not None:
            if len(body) > 1024 * 1024:
                raise ValueError('The chat request exceeds 1 MiB.')
            headers['Content-Type'] = 'application/json'
        path = quote(parts.path.rstrip('/'), safe='/%') + '/' + endpoint
        try:
            connection.connect()
            with self.lock:
                self.socket = connection.sock
            self.check()  # Cancellation while resolving/connecting sends no body.
            connection.request('POST' if payload is not None else 'GET', path, body=body, headers=headers)
            self.check()
            response = connection.getresponse()
            if response.status != 200:
                status = response.status
                response.close()
                if status in (401, 403):
                    raise ValueError('Server authentication failed; check the session API key.')
                if 300 <= status < 400:
                    raise ValueError('Redirects are refused; enter the final trusted API URL.')
                raise ValueError(f'Server rejected the request (HTTP {status}); check model and context settings.')
            return connection, response
        except Exception:
            connection.close()
            self.check()
            raise

    def models(self):
        connection, response = self.request('models')
        try:
            body = response.read(512 * 1024 + 1)
            self.check()
            if len(body) > 512 * 1024:
                raise ValueError('Model list exceeds the response limit.')
            data = json.loads(body)
            rows = data.get('data') if isinstance(data, dict) else None
            if not isinstance(rows, list) or len(rows) > 128:
                raise ValueError('Invalid model list.')
            ids = []
            for row in rows:
                key = row.get('id') if isinstance(row, dict) else None
                if not isinstance(key, str) or not key.strip() or len(key) > 200 or any(ord(c) < 32 for c in key):
                    raise ValueError('Invalid model identity.')
                if key not in ids:
                    ids.append(key)
            return ids
        except Exception:
            self.check()
            raise
        finally:
            response.close()
            connection.close()

    def stream(self, payload, fragment):
        # A file-backed HTTP read can remain blocked after socket.shutdown on
        # Windows. Keep that bounded I/O off the calling worker, so Cancel is
        # observed promptly on every platform. Only the reader owns/ closes the
        # response; closing a buffered reader from another thread can itself
        # block on its I/O lock. Socket reads still have the 15-second timeout.
        events = Queue(maxsize=2)
        completed = Event()
        def publish(kind, value):
            while not completed.is_set() and not self.cancelled.is_set():
                try:
                    events.put((kind, value), timeout=.1)
                    return
                except Full:
                    continue
        def read():
            try:
                result = self._stream(payload, lambda text: publish('text', text))
                publish('done', result)
            except Exception as error:
                if not completed.is_set():
                    publish('error', error)
        worker = Thread(target=read, name='mobile-chat-reader', daemon=True)
        worker.start()
        try:
            while True:
                self.check()
                try:
                    kind, value = events.get(timeout=.1)
                except Empty:
                    continue
                self.check()
                if kind == 'error':
                    raise value
                if kind == 'done':
                    return value
                fragment(value)
        finally:
            completed.set()
            if worker.is_alive():
                self.cancel()

    def _stream(self, payload, fragment):
        connection, response = self.request('chat/completions', payload)
        text, finished, reason = '', False, ''
        deadline = time.monotonic() + 600
        try:
            while True:
                self.check()
                if time.monotonic() >= deadline:
                    raise TimeoutError('Chat generation exceeded ten minutes.')
                line = response.readline(65537)
                self.check()
                if not line:
                    break
                if len(line) > 65536:
                    raise ValueError('Server event exceeds 64 KiB.')
                line = line.decode('utf-8').strip()
                if not line.startswith('data:'):
                    continue
                value = line[5:].strip()
                if value == '[DONE]':
                    finished = True
                    break
                packet = json.loads(value)
                if not isinstance(packet, dict) or 'error' in packet:
                    raise ValueError('Server returned an invalid/error event.')
                choices = packet.get('choices', [])
                if not isinstance(choices, list) or len(choices) > 1:
                    raise ValueError('Only one text response is supported.')
                if not choices:
                    continue  # Optional usage-only event.
                choice = choices[0]
                if not isinstance(choice, dict):
                    raise ValueError('Invalid response choice.')
                delta = choice.get('delta', {})
                if not isinstance(delta, dict) or delta.get('tool_calls') or delta.get('function_call'):
                    raise ValueError('Mobile chat does not execute model tools.')
                content = delta.get('content') or ''
                if not isinstance(content, str):
                    raise ValueError('Only text model replies are supported.')
                text += content
                if len(text.encode('utf-8')) > MAX_REPLY:
                    raise ValueError('Reply exceeds the mobile 256 KiB limit.')
                if content:
                    fragment(content)
                if choice.get('finish_reason') is not None:
                    reason = choice['finish_reason']
                    if reason == 'tool_calls':
                        raise ValueError('Mobile chat does not execute model tools.')
                    finished = True
            if not finished:
                raise ValueError('Connection ended before a complete reply; partial text was preserved.')
            return reason
        except Exception:
            self.check()
            raise
        finally:
            response.close()
            connection.close()
