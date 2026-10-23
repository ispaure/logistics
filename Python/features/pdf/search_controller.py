"""Toolkit-independent PDF search state; adapters own workers and page navigation."""
from dataclasses import dataclass, field
from threading import Event

from .search import Match, Results, result_text


@dataclass(frozen=True)
class SearchRequest:
    """Worker input without document bytes or UI references."""
    query: str
    direction: int
    cancelled: Event = field(default_factory=Event)


@dataclass(frozen=True)
class SearchState:
    query: str
    busy: bool
    status: str
    previous_enabled: bool
    next_enabled: bool


class PDFSearchController:
    """Call on the UI thread; workers only read their request's cancellation event.

    Cancelled work remains busy until its adapter reports completion. Request
    identity prevents old completions from retiring or publishing newer work.
    """
    def __init__(self):
        self.query = ''
        self.results = Results(())
        self.cursor = -1
        self.disposed = False
        self.revision = 0
        self._searched_query = None
        self._pending = None
        self._status = ''

    @property
    def state(self):
        busy = self._pending is not None
        enabled = not self.disposed and not busy
        return SearchState(self.query, busy, self._status, enabled, enabled)

    def set_query(self, text):
        if self.disposed:
            return
        query = ' '.join((text or '').split())
        if query == self.query:
            return
        self.revision += 1
        if self._pending is not None:
            self._pending.cancelled.set()
        self.query = query
        self.results, self.cursor = Results(()), -1
        self._searched_query, self._status = None, ''

    def step(self, direction) -> SearchRequest | Match | None:
        if self.disposed or self._pending is not None or not self.query:
            return None
        if direction not in (-1, 1):
            raise ValueError('Search direction must be -1 or 1.')
        if self._searched_query == self.query:
            return self._move(direction)
        request = SearchRequest(self.query, direction)
        self._pending = request
        self._status = 'Searching PDF…'
        return request

    def _retire(self, request):
        if request is not self._pending:
            return False
        self._pending = None
        if self.disposed or request.cancelled.is_set():
            self._status = ''
            return False
        return True

    def complete(self, request, results) -> Match | None:
        if not self._retire(request):
            return None
        self.results = results
        self._searched_query = request.query
        self.cursor = -1 if request.direction > 0 else 0
        return self._move(request.direction)

    def fail(self, request, error):
        if self._retire(request):
            self._error(error)

    def navigation_failed(self, revision, error):
        if not self.disposed and revision == self.revision:
            self._error(error)

    def _error(self, error):
        self._searched_query = None
        self._status = 'Cannot search PDF: ' + (str(error)[:200] or type(error).__name__)

    def _move(self, direction):
        match = None
        if self.results.matches:
            self.cursor = (self.cursor + direction) % len(self.results.matches)
            match = self.results.matches[self.cursor]
        self._status = result_text(self.results, self.cursor)
        return match

    def dispose(self):
        self.disposed = True
        self.revision += 1
        if self._pending is not None:
            self._pending.cancelled.set()
        self._pending = None
        self.query, self.results, self.cursor = '', Results(()), -1
        self._searched_query, self._status = None, ''
