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
