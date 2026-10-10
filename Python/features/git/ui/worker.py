"""One cancellable job per workspace. Qt owners retain workers until finished."""
from threading import Event
from commonUtils.ui import pyside as qt
from ..runner import GitRunner, GitCancelled, redact


class GitWorker(qt.QThread):
    progress = qt.Signal(str)

    def __init__(self, executable, action, parent=None):
        super().__init__(parent)
        self.action = action
        self.cancel_event = Event()
        self.runner = GitRunner(executable, cancel=self.cancel_event, progress=self.progress.emit)
        self.result = None
        self.error = ''
        self.cancelled = False

    def run(self):
        try:
            self.result = self.action(self.runner)
        except GitCancelled as exc:
            self.cancelled = True
            self.error = str(exc)
        except Exception as exc:
            self.error = redact(str(exc))

    def cancel(self):
        self.cancel_event.set()
