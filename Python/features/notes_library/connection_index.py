"""Bounded session-only parsed connections, shared by a library's documents."""
from contextlib import contextmanager
from threading import Lock, RLock
from commonUtils.runtime.operations import check_cancelled
from .notes import operation

MAX_RETAINED = 8 * 1024 * 1024


class ConnectionIndex:
    def __init__(self):
        self._lock, self._reading = RLock(), Lock()
        self._rows, self._bytes = {}, 0
        self._closed = False
        self._generation = 0

    def invalidate(self):
        with self._lock:
            self._generation += 1
            self._rows.clear()
            self._bytes = 0

    def close(self):
        with self._lock:
            self._closed = True
            self.invalidate()

    @contextmanager
    def reading(self, cancelled):
        # Coalesce simultaneous body reads without blocking UI retirement.
        while not self._reading.acquire(timeout=.05):
            check_cancelled(lambda: self._closed or cancelled())
        try:
            check_cancelled(lambda: self._closed or cancelled())
            yield
        finally:
            self._reading.release()

    def note(self, library, path, *, cancelled=lambda: False):
        from .notes_links import Targets
        requested = cancelled
        cancelled = lambda: self._closed or library._links_closed or requested()
        with self.reading(cancelled), operation(library.provider, cancelled):
            check_cancelled(cancelled)
            before = library.entry(path).get('revision')
            with self._lock:
                generation = self._generation
                cached = self._rows.get(path)
                if before is not None and cached is not None and cached[0] == before:
                    return cached[1]
            data = library.read(path, cancelled=cancelled)
            text = data.decode('utf-8-sig')
            value = dict(size=len(data), words=len(text.split()), characters=len(text),
                         targets=frozenset(Targets(text).targets))
            check_cancelled(cancelled)
            # No note bodies are retained. Providers without revisions are read
            # afresh; changing files and invalidated scans never populate cache.
            cost = sum(len(target.encode('utf-8')) + 64 for target in value['targets']) + len(path.encode('utf-8')) + 256
            after = library.entry(path).get('revision')
            with self._lock:
                check_cancelled(cancelled)
                if (generation == self._generation and before is not None and before == after
                        and cost <= MAX_RETAINED):
                    previous = self._rows.pop(path, None)
                    if previous is not None:
                        self._bytes -= previous[2]
                    if self._bytes + cost > MAX_RETAINED or len(self._rows) >= 5000:
                        self._rows.clear()
                        self._bytes = 0
                    self._rows[path] = before, value, cost
                    self._bytes += cost
            return value
