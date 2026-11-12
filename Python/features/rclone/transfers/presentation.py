"""Bounded display models; transfer authorization stays in ReviewSession."""
from pathlib import PurePosixPath
from time import monotonic

PAGE_SIZE = 30
KINDS = ('all', 'add', 'replace', 'delete', 'cleanup')


def workspace_name(source, destination, operation):
    local = source if operation == 'Push' else destination
    parts = local.replace('\\', '/').rstrip('/').split('/')
    return parts[1] if parts and parts[0] in ('Local', 'LocalCrypt') and len(parts) > 1 else PurePosixPath(local).name or local


class ReviewProjection:
    def __init__(self, request):
        self.request = request
        self.snapshot = None
        self.kind, self.query, self.page = 'all', '', 0
        self._rows = ()
        self._key = None
        self._counted = None
        self._counts = {}

    def select(self, *, kind=None, query=None, step=0):
        if kind is not None or query is not None:
            self.kind = kind if kind in KINDS else 'all'
            self.query = (query or '')[:1000]
            self.page = 0
        else:
            self.page = max(0, self.page + step)

    def model(self, snapshot, *, state, can_confirm, can_early):
        self.snapshot = snapshot
        if self._counted is not snapshot:
            self._counts = snapshot.counts
            self._counted = snapshot
        key = (snapshot, self.kind, self.query)
        if key != self._key:
            self._rows = snapshot.rows(self.kind, self.query)
            self._key = key
        self.page = min(self.page, max(0, (len(self._rows) - 1) // PAGE_SIZE))
        notices = dict(scanning='Comparing files… Nothing has changed yet.', ready='',
            checking='Checking that this review is still current…', stopping='Stopping comparison…',
            changed='Files changed. Review the updated results before confirming again.',
            failed='Comparison failed: ' + snapshot.error)
        request = self.request
        return dict(mode='review', operation=request.operation, source=request.source,
            destination=request.destination, workspace=workspace_name(request.source, request.destination, request.operation),
            counts=self._counts, rows=self._rows[self.page * PAGE_SIZE:(self.page + 1) * PAGE_SIZE],
            total=len(self._rows), page=self.page, page_size=PAGE_SIZE, filter=self.kind, query=self.query,
            complete=snapshot.complete, notice=notices.get(state, ''),
            can_confirm=bool(snapshot.complete and can_confirm), can_early=can_early)

    def clear(self):
        self.snapshot = self._key = self._counted = None
        self._counts = {}
        self._rows = ()
        self.query = ''


def removal_counts(values):
    counts = (f'{values[key]:,} {label}' for key, label in (
        ('file_delete_attempts', 'files'), ('folder_removal_attempts', 'folders'))
        if values.get(key) is not None)
    return ', '.join(counts) or 'Not reported'


def progress_model(state):
    if state.display_revoked:
        return dict(mode='progress', operation='Pull', source='—', destination='—', workspace='Transfer',
            phase='failed', busy=False, message='Connection locked or changed. Review again after unlocking.',
            status='', percentage=None, done=0, total=0, files=0, total_files=0, checks=0, listed=0,
            file_delete_attempts=None, folder_removal_attempts=None,
            active=0, active_files=(), attempt=0, max_attempts=0, retrying=False, elapsed=0)
    values = state.metrics
    phase = values.get('phase', '')
    removing = phase == 'Removing destination entries'
    result = state.result
    if state.busy:
        phase = ('verify' if phase in ('Sync complete; verifying local copy', 'Checking / finishing sync')
                 else 'transfer' if removing or phase == 'Transferring' or values.get('done', 0) > 0 else 'scan')
        if state.cancel is not None and state.cancel.is_set():
            phase = 'stopping'
    else:
        phase = result if result in ('complete', 'failed', 'cancelled', 'conflict') else 'idle'
    elapsed = max(0, int((state.finished_at or monotonic()) - state.started_at)) if state.started_at else 0
    source, destination = state.endpoints or ('—', '—')
    operation = state.operation.capitalize() if state.operation in ('push', 'pull') else 'Download'
    percentage = state.percentage if phase == 'transfer' else 100 if phase == 'complete' else None
    return dict(mode='progress', operation=operation, source=source, destination=destination,
        workspace=workspace_name(source, destination, operation), phase=phase, busy=state.busy,
        message=state.message, status={'stopping': 'Stopping transfer…'}.get(phase,
            'Removing destination entries…' if removing else 'Copying files…'),
        percentage=percentage, done=values.get('done', 0), total=values.get('total', 0),
        files=values.get('files', 0), total_files=values.get('total_files', 0),
        file_delete_attempts=values.get('file_delete_attempts'),
        folder_removal_attempts=values.get('folder_removal_attempts'),
        checks=values.get('checks', 0), listed=values.get('listed', 0), active=values.get('active', 0),
        active_files=tuple(dict(row) for row in values.get('active_files', ())[:3]) if phase == 'transfer' else (),
        attempt=values.get('attempt', 0), max_attempts=values.get('max_attempts', 0),
        retrying=values.get('retrying', False), elapsed=elapsed)
