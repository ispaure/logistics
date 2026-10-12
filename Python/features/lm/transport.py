"""Asynchronous Qt HTTP transport; no workers, SDK or tools execution."""
import json
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from .domain import MAX_TEXT, base_url


class StreamDecoder:
    """SSE framing accepts arbitrary UTF-8/network boundaries and CRLF lines."""
    def __init__(self):
        self.buffer = b''
        self.lines = []
        self.done = False
        self.finished = False
        self.finish_reason = None
        self.usage = None
        self.text = ''

    def feed(self, chunk):
        self.buffer += chunk
        if len(self.buffer) + sum(map(len, self.lines)) > 2 * 1024 * 1024:
            raise ValueError('Server stream record exceeds the size limit.')
        fragments = []
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            line = line.rstrip(b'\r')
            if line:
                if line.startswith(b'data:'):
                    self.lines.append(line[5:].lstrip(b' '))
            elif self.lines:
                value = b'\n'.join(self.lines).decode('utf-8')
                self.lines.clear()
                if value == '[DONE]':
                    self.done = True
                    continue
                if self.done:
                    raise ValueError('Server sent data after the end of the response.')
                event = json.loads(value)
                if not isinstance(event, dict) or 'error' in event:
                    raise ValueError('Server returned an invalid response or generation error.')
                if isinstance(event.get('usage'), dict):
                    self.usage = event['usage']
                choices = event.get('choices', [])
                if not isinstance(choices, list):
                    raise ValueError('Invalid response choices.')
                if not choices:
                    continue
                choice = choices[0]
                delta = choice.get('delta', {})
                if not isinstance(delta, dict):
                    raise ValueError('Invalid response delta.')
                if delta.get('tool_calls') or choice.get('finish_reason') in ('tool_calls', 'function_call'):
                    raise ValueError('This chat client does not execute model tools.')
                text = delta.get('content') or ''
                if not isinstance(text, str):
                    raise ValueError('Only text responses are supported.')
                if len(self.text) + len(text) > MAX_TEXT:
                    raise ValueError('Response exceeds the text size limit.')
                self.text += text
                fragments.append(text)
                if choice.get('finish_reason') is not None:
                    self.finished = True
                    self.finish_reason = choice['finish_reason']
        return ''.join(fragments)


class Client(QObject):
    delta = Signal(str)
    models = Signal(list)
    completed = Signal(str, str, object)  # status, safe error, metadata

    def __init__(self, parent=None, *, timeout_ms=None):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self.reply = None
        self.mode = None
        self.cancelled = False
        self.failure = ''
        self.decoder = None
        self.body = b''
        self.total_bytes = 0
        self.pending = ''
        self.delivered_chars = 0
        if timeout_ms is None:
            from commonUtils.configuration.settings import get_setting
            seconds = get_setting('Connection', 'timeout_seconds_int', 180,
                                  path=Path(__file__).with_name('config.ini'), minimum=5, maximum=3600)
            timeout_ms = seconds * 1000
        self.timeout_ms = timeout_ms
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self._timed_out)
        self.flush_timer = QTimer(self)
        self.flush_timer.setInterval(50)
        self.flush_timer.timeout.connect(self._flush)

    @property
    def busy(self):
        return self.reply is not None

    def start(self, profile, token='', payload=None):
        if self.busy:
            raise ValueError('An LM request is already running.')
        url = base_url(profile['base_url']) + ('/models' if payload is None else '/chat/completions')
        if any(ord(c) < 32 or ord(c) > 126 for c in token):
            raise ValueError('API tokens must contain printable ASCII characters.')
        request = QNetworkRequest(QUrl(url))
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        request.setTransferTimeout(self.timeout_ms)
        request.setRawHeader(b'Accept', b'application/json' if payload is None else b'text/event-stream')
        if token:
            request.setRawHeader(b'Authorization', ('Bearer ' + token).encode('ascii'))
        self.mode = 'models' if payload is None else 'chat'
        self.body = b''
        self.total_bytes = 0
        self.decoder = StreamDecoder()
        self.pending = ''
        self.delivered_chars = 0
        self.cancelled = False
        self.failure = ''
        if payload is None:
            self.reply = self.manager.get(request)
        else:
            request.setRawHeader(b'Content-Type', b'application/json')
            self.reply = self.manager.post(request, json.dumps(payload, allow_nan=False).encode('utf-8'))
        self.reply.readyRead.connect(self._read)
        self.reply.finished.connect(self._finished)
        self.timeout.start(self.timeout_ms)
        self.flush_timer.start()

    def cancel(self):
        if self.reply is not None:
            self.cancelled = True
            self.reply.abort()

    def _timed_out(self):
        if self.reply is not None:
            self.failure = 'Server timed out without sending data. Check the server or increase the inactivity timeout in Settings.'
            self.reply.abort()

    def _flush(self):
        if self.pending:
            text, self.pending = self.pending, ''
            self.delivered_chars += len(text)
            self.delta.emit(text)

    def _read(self):
        if self.reply is None or not self.reply.isOpen():
            return
        chunk = bytes(self.reply.readAll())
        if not chunk:
            return
        self.timeout.start(self.timeout_ms)
        self.total_bytes += len(chunk)
        status = self.reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if status is not None and status != 200:
            return  # Never expose a server error body that could echo credentials.
        try:
            if self.total_bytes > 32 * 1024 * 1024:
                raise ValueError('Server response exceeds the size limit.')
            content_type = bytes(self.reply.rawHeader(b'Content-Type')).lower()
            if self.mode == 'chat' and b'text/event-stream' in content_type:
                self.pending += self.decoder.feed(chunk)
            else:
                self.body += chunk
                if len(self.body) > 2 * 1024 * 1024:
                    raise ValueError('Server JSON response exceeds the size limit.')
        except (ValueError, UnicodeError, TypeError, AttributeError, KeyError):
            # feed() may have accepted earlier records before rejecting this chunk.
            # Preserve all decoded text, including anything not yet flushed to UI.
            if self.mode == 'chat':
                self.pending = self.decoder.text[self.delivered_chars:]
            self.failure = 'Invalid, unsupported or oversized server response. Check the server API and model.'
            self.reply.abort()

    def _finished(self):
        self._read()
        self._flush()
        reply, self.reply = self.reply, None
        self.timeout.stop()
        self.flush_timer.stop()
        code = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        status, error = 'complete', self.failure
        metadata = {}
        try:
            if self.cancelled:
                status = 'cancelled'
            elif error:
                status = 'failed'
            elif code != 200:
                hints = {401: 'Authentication failed; check the session API token.',
                         403: 'Server denied access.', 404: 'Endpoint or model not found; check the API base URL and model ID.',
                         400: 'Server rejected the request; check model parameters and context size.',
                         429: 'Server is busy or rate limited; retry later.'}
                error = hints.get(code, f'Server request failed (HTTP {code or "unavailable"}). Check the server connection.')
                status = 'failed'
            elif reply.error() != QNetworkReply.NetworkError.NoError:
                status, error = 'failed', 'Connection ended before the response completed.'
            elif self.mode == 'models':
                data = json.loads(self.body)
                entries = data['data']
                if not isinstance(entries, list):
                    raise ValueError('Invalid models list')
                ids = [entry['id'] for entry in entries]
                if any(not isinstance(key, str) for key in ids):
                    raise ValueError('Invalid model IDs')
                self.models.emit(sorted(set(ids)))
            elif self.body:
                data = json.loads(self.body)
                choice = data['choices'][0]
                if choice['message'].get('tool_calls'):
                    raise ValueError('Unsupported tool call')
                text = choice['message']['content']
                if not isinstance(text, str) or len(text) > MAX_TEXT:
                    raise ValueError('Invalid text')
                self.delta.emit(text)
                metadata = {'finish_reason': choice.get('finish_reason'), 'usage': data.get('usage')}
            elif not (self.decoder.done or self.decoder.finished):
                status, error = 'failed', 'Server stream ended without a completion marker. Partial output was kept.'
            else:
                metadata = {'finish_reason': self.decoder.finish_reason, 'usage': self.decoder.usage}
        except (ValueError, UnicodeError, TypeError, KeyError, IndexError, AttributeError):
            status, error = 'failed', 'Server returned an unsupported response. Verify an OpenAI-compatible text API.'
        finally:
            reply.deleteLater()
        self.completed.emit(status, error, metadata)
