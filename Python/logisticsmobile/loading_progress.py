"""Logistics loading-panel policy over explicit shared read progress."""
from contextlib import contextmanager
from contextvars import ContextVar
from commonUtils.runtime.progress import CoalescedProgress
from commonUtils.runtime.streams.progress import reading_stream as measured_stream, ReadingProvider

current_progress = ContextVar('file_opening_progress', default=None)


class OpeningProgress(CoalescedProgress):
    def __init__(self, app, state, bar, label):
        self.bar, self.label = bar, label
        super().__init__(app.loop, self.update,
                         active=lambda: getattr(app, '_file_loading', None) is state)

    def update(self, completed, total):
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


@contextmanager
def reading_stream(stream, *, total=None):
    reporter = current_progress.get()
    with measured_stream(stream, total=total,
                         progress=reporter.publish if reporter is not None else None) as incoming:
        yield incoming


def file_sha256(path):
    from pathlib import Path
    from commonUtils.runtime.streams import stream_signature
    with Path(path).open('rb') as stream, reading_stream(stream) as incoming:
        return stream_signature(incoming)[1]


def opening_options(copies):
    from features.text_editor.resources import LocalTextCopies
    if current_progress.get() is not None and type(copies) is LocalTextCopies:
        return dict(read_provider=ReadingProvider(copies.provider, progress=current_progress.get().publish))
    return {}
