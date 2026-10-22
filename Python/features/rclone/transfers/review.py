"""Shared, memory-only transfer review state for desktop and mobile hosts."""
from dataclasses import dataclass
from threading import Event, Lock, Thread

from features.rclone.transfers.transfer_options import TransferOptions


@dataclass(frozen=True)
class ReviewRequest:
    operation: str
    source: str
    destination: str
    binding: str
    options: TransferOptions = TransferOptions()

    def __post_init__(self):
        if self.operation not in ('Push', 'Pull') or not all((self.source, self.destination, self.binding)):
            raise ValueError('Review requires a direction, source, destination and connection binding.')

    def confirmation(self, *, incomplete=False):
        return (f'From: {self.source}\nTo: {self.destination}\n\n'
                + f'Rename tracking: {"on" if self.options.track_renames else "off"}. '
                + f'Bandwidth: {str(self.options.bw_limit) + " MB/s" if self.options.bw_limit else "unlimited"}. '
                + f'Push exclusions: {len(self.options.excludes)}.\n'
                + ('The comparison is incomplete. Additional replacements and deletions may occur.\n' if incomplete else '')
                + 'Sync replaces or deletes destination files to match the source. There is no backup or undo. Continue?')


@dataclass(frozen=True)
class ReviewSnapshot:
    changes: tuple
    complete: bool
    fingerprint: str
    error: str = ''

    def text(self):
        counts = {kind: sum(action == kind for action, _ in self.changes) for kind in ('add', 'replace', 'delete')}
        heading = ('Review complete' if self.complete else 'Partial review — incomplete')
        cleanups = sum(action == 'cleanup' for action, _ in self.changes)
        summary = f'{counts["add"]} additions · {counts["replace"]} replacements · {counts["delete"]} deletions'
        if cleanups:
            summary += f' · {cleanups} local generated files to remove before Push'
        rows = [f'{kind.capitalize()}: {path}' for kind, path in self.changes if kind != 'match']
        return '\n'.join([heading, summary, self.error, *rows])


class ReviewScan:
    """A scanner emits (kind, path) and returns a comparison fingerprint.

    Cancellation retires the scan before a host starts transfer work. Stopping a
    comparison never authorizes a write, even if it happened after completion.
    """
    def __init__(self, scanner):
        self.cancelled = Event()
        self.retired = Event()
        self.lock = Lock()
        self.changes = {}
        self.complete, self.fingerprint, self.error = False, '', ''
        self.thread = Thread(target=self._run, args=(scanner,), daemon=True)
        self.thread.start()

    def emit(self, kind, path):
        if kind not in ('add', 'replace', 'delete', 'match', 'cleanup') or not isinstance(path, str):
            raise ValueError('Invalid comparison result.')
        with self.lock:
            key = ('cleanup' if kind == 'cleanup' else 'transfer', path)
            self.changes[key] = (kind, path)

    def replace(self, changes):
        # Validate away from the live state, then publish a whole attempt at once.
        rows = {}
        for kind, path in changes:
            if kind not in ('add', 'replace', 'delete', 'match', 'cleanup') or not isinstance(path, str):
                raise ValueError('Invalid comparison result.')
            rows[('cleanup' if kind == 'cleanup' else 'transfer', path)] = (kind, path)
        with self.lock:
            self.changes = rows

    def _run(self, scanner):
        try:
            def emit(kind, path):
                self.emit(kind, path)
            emit.replace = self.replace
            fingerprint = scanner(emit, self.cancelled.is_set)
            with self.lock:
                if not self.cancelled.is_set():
                    if not fingerprint:
                        raise ValueError('Comparison did not return a valid revision.')
                    self.fingerprint, self.complete = fingerprint, True
        except Exception as error:
            with self.lock:
                if not self.cancelled.is_set():
                    self.error = str(error)
        finally:
            self.retired.set()

    def snapshot(self):
        with self.lock:
            return ReviewSnapshot(tuple(sorted(self.changes.values())),
                                  self.complete, self.fingerprint, self.error)

    def stop(self):
        self.cancelled.set()


def unchanged(review, checked):
    return (review.complete and checked.complete and not review.error and not checked.error
            and review.fingerprint == checked.fingerprint and review.changes == checked.changes)


def replace_changes(emit, changes):
    """Publish an authoritative snapshot; retain simple callable test adapters."""
    replace = getattr(emit, 'replace', None)
    if replace is not None:
        replace(changes)
    else:
        for kind, path in changes:
            emit(kind, path)


class ReviewSession:
    """One approval owner; a retired scan and current binding precede execution.

    A completed approval triggers a fresh comparison. Explicit incomplete approval
    remains a separate user decision and still waits for cancellation retirement.
    """
    def __init__(self, request, scanner, valid=lambda: True):
        self.request, self.scanner, self.valid = request, scanner, valid
        self.scan = ReviewScan(scanner)
        self.expected = None
        self.decision = None
        self.state = 'scanning'

    def can_approve(self, *, incomplete=False):
        return (self.decision is None and self.expected is None and self.valid()
                and (incomplete or self.scan.retired.is_set() and self.scan.snapshot().complete))

    def approve(self, *, incomplete=False):
        # Called only after the platform's explicit destructive-action dialog.
        if not self.valid():
            self.cancel()
            return False
        if not self.can_approve(incomplete=incomplete):
            return False
        if incomplete:
            self.decision = 'proceed'
            self.scan.stop()
            self.state = 'stopping'
        else:
            self.expected = self.scan.snapshot()
            self.scan = ReviewScan(self.scanner)
            self.state = 'checking'
        return True

    def cancel(self):
        self.decision = 'cancel'
        self.scan.stop()
        self.state = 'stopping'

    def poll(self):
        if not self.valid() or self.scan.cancelled.is_set() and self.decision is None:
            self.cancel()
        snapshot = self.scan.snapshot()
        if self.decision is not None:
            self.state = ('approved' if self.decision == 'proceed' and self.valid() else 'cancelled'
                          ) if self.scan.retired.is_set() else 'stopping'
        elif self.expected is not None and self.scan.retired.is_set():
            if unchanged(self.expected, snapshot) and self.valid():
                self.decision, self.state = 'proceed', 'approved'
            else:
                self.expected, self.state = None, 'changed'
        elif self.expected is None and self.state != 'changed':
            self.state = 'failed' if snapshot.error else 'ready' if snapshot.complete else 'scanning'
        return self.state

    @property
    def approved(self):
        return self.poll() == 'approved'
