"""Git cancellation and redaction policy around the shared result worker."""
from threading import Event
from commonUtils.ui import pyside as qt
from commonUtils.ui.operations import ResultWorker
from ..runner import GitRunner, GitCancelled, redact


class GitWorker(ResultWorker):
    progress = qt.Signal(str)

    def __init__(self, executable, action, parent=None):
        super().__init__(lambda: action(self.runner), parent,
                         error_formatter=lambda error: str(error) if isinstance(error, GitCancelled) else redact(str(error)),
                         cancellation_errors=(GitCancelled,))
        self.action = action
        self.cancel_event = Event()
        self.runner = GitRunner(executable, cancel=self.cancel_event, progress=self.progress.emit)

    def cancel(self):
        self.cancel_event.set()
        super().cancel()
