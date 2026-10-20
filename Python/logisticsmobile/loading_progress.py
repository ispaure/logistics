"""Measured read progress for the current opening task, including its workers."""
from contextlib import contextmanager
from contextvars import ContextVar
import os
import stat
from threading import Lock

current_progress = ContextVar('file_opening_progress', default=None)


class OpeningProgress:
    def __init__(self, app, state, bar, label):
        self.app, self.state, self.bar, self.label = app, state, bar, label
        self.lock = Lock()
        self.closed = self.pending = False
        self.latest = None
        self.handle = None

    def publish(self, completed=None, total=None):
        with self.lock:
            if self.closed:
                return
            self.latest = completed, total
            if self.pending:
                return
            self.pending = True
        self.app.loop.call_soon_threadsafe(self.schedule)

    def schedule(self):
        if not self.closed:
            self.handle = self.app.loop.call_later(.05, self.flush)

    def flush(self):
        with self.lock:
            self.pending = False
            latest = self.latest
        if self.closed or getattr(self.app, '_file_loading', None) is not self.state:
            return
        completed, total = latest
        measured = completed is not None and total is not None and total > 0 and completed <= total
        if measured:
            self.bar.stop()
            self.bar.max = total
            self.bar.value = completed
            self.label.text = f'Reading {completed * 100 // total}%'
        else:
            if self.bar.max is not None:
                self.bar.max = None
                self.bar.start()
            self.label.text = 'Preparing document…' if completed is None else 'Reading file…'

    def close(self):
        with self.lock:
            self.closed = True
        if self.handle is not None:
            self.handle.cancel()


class ReadingStream:
    def __init__(self, stream, reporter, total):
        self.stream, self.reporter, self.total = stream, reporter, total
        self.completed = 0

    def __getattr__(self, name):
        return getattr(self.stream, name)

    def read(self, size=-1):
        # Bound individual reads even when a text reader asks for the whole file.
        remaining = -1 if size is None else size
        chunks = []
        while remaining != 0:
            chunk = self.stream.read(64 * 1024 if remaining < 0 else min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            self.completed += len(chunk)
            self.reporter.publish(self.completed, self.total)
            if remaining > 0:
                remaining -= len(chunk)
        return b''.join(chunks)


@contextmanager
def reading_stream(stream, *, total=None):
    reporter = current_progress.get()
    if reporter is None:
        yield stream
        return
    if total is None:
        try:
            info = os.fstat(stream.fileno())
            if stat.S_ISREG(info.st_mode):
                total = max(0, info.st_size - stream.tell())
        except (AttributeError, OSError, ValueError):
            pass
    if type(total) is not int or total < 0:
        total = None
    reporter.publish(0, total)
    try:
        yield ReadingStream(stream, reporter, total)
    finally:
        reporter.publish()


def file_sha256(path):
    from pathlib import Path
    from commonUtils.runtime.streams import stream_signature
    with Path(path).open('rb') as stream, reading_stream(stream) as incoming:
        return stream_signature(incoming)[1]


class ReadingProvider:
    def __init__(self, provider):
        self.provider = provider

    def __getattr__(self, name):
        return getattr(self.provider, name)

    @contextmanager
    def open(self, path):
        total = self.provider.entry(path).get('size')
        with self.provider.open(path) as stream, reading_stream(stream, total=total) as incoming:
            yield incoming


def opening_options(copies):
    from features.text_editor.resources import LocalTextCopies
    if current_progress.get() is not None and type(copies) is LocalTextCopies:
        return dict(read_provider=ReadingProvider(copies.provider))
    return {}
