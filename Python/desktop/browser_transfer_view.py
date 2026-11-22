"""Show browser filesystem work in the desktop process workspace."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.ui import pyside as qt
from commonUtils.ui.tasks.process_progress import (
    ProcessProgressPresentation, ProcessProgressWindow, present_process_window,
)
from commonUtils.ui.tasks.process_runner import ProcessResult, ProcessUpdate


class BrowserTransferStatus(qt.QObject):
    output = qt.Signal(str)
    status = qt.Signal(str, int, str)
    progress = qt.Signal(object)
    completed = qt.Signal(object)

    def __init__(self, operation, *, private=False):
        super().__init__()
        self.operation = operation
        self.private = private
        self.busy = True
        operation.progress_changed.connect(self._progress)
        operation.completed.connect(self._finish)

    def cancel(self):
        if self.busy:
            self.operation.request_cancel()
            self.status.emit('running', 1, 'Cancelling safely…')

    def _progress(self, done, total, message):
        if self.busy and not self.operation.cancelled.is_set():
            self.progress.emit(ProcessUpdate(done, total))
            self.status.emit('running', 1, message)

    def _finish(self, result, error):
        self.busy = False
        self.operation.progress_changed.disconnect(self._progress)
        self.operation.completed.disconnect(self._finish)
        issues = (error,) if error else result.issues if result is not None else ()
        completed = len(result.completed) if result is not None else 0
        if result is not None and result.cancelled:
            state = 'cancelled'
        elif error or result is None or result.failed:
            state = 'failed'
        else:
            state = 'succeeded'
        if issues:
            self.output.emit('\n'.join(issues))
        message = f'{completed} item(s) transferred.'
        if state == 'cancelled':
            message = 'Cancelled. ' + message
        if issues:
            message += ' ' + issues[0]
        self.status.emit(state, 1, message)
        diagnostic = ('Open Workspace actions for transfer details.' if self.private and issues
                      else '\n'.join(issues))
        self.completed.emit(ProcessResult(state, None, 1, diagnostic))


def present_browser_transfer(operation, title, *, provider=None):
    private = getattr(provider, 'private', False)
    status = BrowserTransferStatus(operation, private=private)
    window = ProcessProgressWindow(f'Transfers · {title}', runner=status,
                                   presentation=ProcessProgressPresentation, context={'notify_transfer': True})
    if private:
        from services.documents.ui.private_views import protect_private_view
        protect_private_view(window, provider)
    status.status.emit('running', 1, 'Preparing transfer…')
    present_process_window(window)
    return window
