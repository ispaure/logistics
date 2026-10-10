"""Logistics archive jobs, credential retries and worker-safe shutdown."""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import zipfile

from commonUtils.ui import pyside as qt
from commonUtils.ui.operation_progress import OperationProgress
from commonUtils.runtime.operations import OperationCancelled
from services.zip_passwords import resolve_password, is_password_error, remember_verified_password
from ui_new.dialogs.archive_password import ask_password


@dataclass(frozen=True)
class ArchiveJob:
    kind: str
    path: Path
    work: Callable
    unlock: bool = False


class ArchiveSession(qt.QObject):
    completed = qt.Signal(str, object, object, str)
    state_changed = qt.Signal()
    idle = qt.Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.host = parent
        self.task = OperationProgress(parent)
        self.task.completed.connect(self._completed)
        self.closing = False
        self._pending = None
        self._retry = None

    @property
    def busy(self):
        return self.task.busy or self._retry is not None

    def start(self, kind, work, path, *, unlock=False, password=None):
        if self.busy or self.closing:
            return False
        request = ArchiveJob(kind, Path(path), work, unlock)
        self._pending = request
        def job(progress, cancelled):
            try:
                secret = resolve_password(request.path, password=password, cancelled=cancelled) if unlock and zipfile.is_zipfile(request.path) else password
                result = request.work(progress, cancelled, secret)
                if kind in ('edit', 'create') and result is not None and secret:
                    remember_verified_password(result, secret)
                return result
            except OperationCancelled:
                return None
        self.task.start(job, message={
            'open': 'Reading archive headers…', 'create': 'Creating and verifying archive…',
            'extract': 'Preparing extraction…', 'test': 'Checking every entry…',
            'preview': 'Reading preview…', 'edit': 'Rebuilding and verifying ZIP…',
        }[kind])
        self.state_changed.emit()
        return True

    def _completed(self, result, error):
        request, self._pending = self._pending, None
        self.task.hide()
        if error and request.unlock and is_password_error(error) and not self.closing:
            password = ask_password(request.path, error, self.host)
            if password is not None:
                self._retry = request, password
                qt.QTimer.singleShot(0, self, self._retry_job)
                return
        self.completed.emit(request.kind, request.path, result, error)
        self.state_changed.emit()
        self.idle.emit()

    def _retry_job(self):
        retry, self._retry = self._retry, None
        if retry and not self.closing:
            request, password = retry
            self.start(request.kind, request.work, request.path, unlock=request.unlock, password=password)
        else:
            self.state_changed.emit()
            self.idle.emit()

    def prepare_close(self):
        self.closing = True
        self._retry = None
        if self.task.busy:
            self.task.request_cancel()
            return False
        return True
