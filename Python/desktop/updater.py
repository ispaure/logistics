"""Quiet update checks and an explicit, cooperative update/restart action."""
import json
import shutil
from time import monotonic

from commonUtils.ui import pyside as qt
from commonUtils.ui.tasks.operation_progress import OperationProgress
from features.preferences import preferences_path
from services import updates
from .notifications import notify


class UpdateController(qt.QObject):
    idle = qt.Signal()

    def __init__(self, owner):
        super().__init__(owner.dlg)
        self.owner = owner
        self.available = None
        self.selected = None
        self.last_check = 0
        self.operation = ''
        self.progress = OperationProgress(owner.dlg)
        self.progress.hide()
        self.progress.completed.connect(self._finished)
        self.progress.completed.connect(lambda *args: self.idle.emit())
        self.button = owner.launch_surface.update_button
        self.button.clicked.connect(self.install)
        self.timer = qt.QTimer(self)
        self.timer.setInterval(15000)
        self.timer.timeout.connect(self.poll)
        self.timer.start()
        result = preferences_path().parent / 'state/updates/last-result.json'
        if result.is_file():
            try:
                outcome = json.loads(result.read_text(encoding='utf-8'))
                if not isinstance(outcome, dict) or not isinstance(outcome.get('success'), bool):
                    raise ValueError('Invalid update receipt outcome')
                if not outcome['success']:
                    if not isinstance(outcome.get('message'), str):
                        raise ValueError('Invalid update receipt message')
                    notify('updates', 'Logistics update failed', outcome['message'], outcome='failure')
                result.unlink()
            except (OSError, ValueError, KeyError):
                pass
        qt.QTimer.singleShot(0, self.poll)

    def poll(self):
        if self.progress.busy or self.owner._closing:
            return
        try:
            selected = updates.choice()
        except ValueError:
            return
        if selected != self.selected:
            self.available = None
            self.last_check = 0
            self.selected = selected
            self.owner._update_offer_visibility()
        if not selected.enabled or monotonic() - self.last_check < 900:
            return
        self.last_check = monotonic()
        self.operation = 'check'
        self.progress.start(lambda report, cancelled: updates.check(), show_progress=False)

    def install(self):
        if self.progress.busy or self.available is None:
            return
        self.operation = 'prepare'
        self.button.setText('Preparing update…')
        self.button.setEnabled(False)
        self.owner.launch_surface.position_settings()
        available = dict(self.available)
        self.progress.start(lambda report, cancelled: updates.prepare(available), show_progress=False)

    def _finished(self, result, error):
        self.button.setText('Update Logistics')
        self.button.setEnabled(True)
        self.owner.launch_surface.position_settings()
        if self.progress.cancelled.is_set():
            # A cancelled preparation must never apply on a later normal exit.
            if self.operation == 'prepare' and result is not None:
                shutil.rmtree(result.parent, ignore_errors=True)
            return
        if error:
            if self.operation == 'prepare':
                notify('updates', 'Could not prepare Logistics update', error, outcome='failure')
            return  # Network checks remain quiet when offline.
        if self.operation == 'check':
            try:
                if updates.choice() != self.selected:
                    self.last_check = 0
                    return
            except ValueError:
                return
            self.available = result
            self.owner._update_offer_visibility()
        else:
            try:
                selected = updates.choice()
            except ValueError:
                selected = None
            if selected is None or selected != self.selected:
                shutil.rmtree(result.parent, ignore_errors=True)
                self.last_check = 0
                return
            self.owner.pending_update = result
            self.owner.dlg.close()
            if self.owner.pending_update is None:
                shutil.rmtree(result.parent, ignore_errors=True)

    def prepare_close(self):
        if self.progress.busy:
            self.progress.request_cancel()
            return False
        self.timer.stop()
        return True
