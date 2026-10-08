"""Assess on opening, then encrypt a fixed selection with configured passwords."""
from threading import Event
from commonUtils.ui import pyside as qt
from commonUtils.ui.operations import Operation
from features.comics.encryption import plan_encryption, execute_encryption


class EncryptComicsDialog(qt.QDialog):
    progress_changed = qt.Signal(int, int, object)
    def __init__(self, targets, parent=None):
        super().__init__(parent)
        self.targets = tuple(targets)
        self.busy = False
        self.plan = None
        self.completed = False
        self.encrypting = False
        self.cancel_requested = Event()
        self.progress_changed.connect(self._progress)
        self.setWindowTitle('Encrypt unencrypted comics')
        layout = qt.QVBoxLayout(self)
        description = qt.QLabel('Encrypt unencrypted CBZ files in the selection, including nested folders. '
                               'Existing encrypted comics are skipped. Names and file contents are preserved. '
                               'Each comic requires a password configured in remoteConfig.ini.')
        description.setWordWrap(True)
        layout.addWidget(description)
        self.message = qt.QLabel()
        self.message.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.progress_bar = qt.QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        self.cancel_button = qt.QPushButton('Cancel after current comic')
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel)
        layout.addWidget(self.cancel_button)
        self.start_button = qt.QPushButton('Encrypt comics')
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self._start)
        layout.addWidget(self.start_button)
        self.resize(600, 260)
        qt.QTimer.singleShot(0, self._assess)

    def _run(self, work, completed):
        self.busy = True
        self.start_button.setEnabled(False)
        self.cancel_requested.clear()
        self.cancel_button.setEnabled(self.encrypting)
        operation = Operation(work, self)
        self.operation = operation
        operation.completed.connect(completed)
        operation.finished.connect(lambda: self._finished(operation))
        operation.start()

    def _finished(self, operation):
        self.busy = False
        self.encrypting = False
        self.cancel_button.setEnabled(False)
        operation.deleteLater()
        if not self.completed:
            self.start_button.setText('Encrypt comics' if self.plan is not None else 'Check selected comics')
            self.start_button.setEnabled(True)

    def _assess(self):
        if self.busy or self.completed or self.plan is not None:
            return
        self.progress_bar.setRange(0, 0)
        self.message.setText('Checking selected comics…')
        self._run(lambda: plan_encryption(self.targets), self._planned)

    def _start(self):
        if self.busy or self.completed:
            return
        if self.plan is None:
            self._assess()
        else:
            if self.plan.missing:
                self.message.setText('Cannot continue: one or more comics have no password configured in remoteConfig.ini.')
                return
            plan = self.plan
            self.plan = None
            self.message.setText('Encrypting and verifying comics…')
            self.encrypting = True
            self.progress_bar.setRange(0, max(1, len(plan.passwords)))
            self.progress_bar.setValue(0)
            self._run(lambda: execute_encryption(plan, progress=self.progress_changed.emit,
                                                 cancelled=self.cancel_requested.is_set), self._completed)

    def _cancel(self):
        if self.busy and self.encrypting:
            self.cancel_requested.set()
            self.cancel_button.setEnabled(False)
            self.message.setText('Cancellation requested. Finishing and verifying the current comic…')

    def _progress(self, completed, total, path):
        self.progress_bar.setRange(0, max(1, total))
        self.progress_bar.setValue(completed)
        self.progress_bar.setFormat(f'{completed} / {total} comics completed')
        if not self.cancel_requested.is_set():
            self.message.setText(f'Encrypting and verifying {path}' if path else f'{completed} / {total} comics completed')

    def _planned(self, plan, error):
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        if error:
            self.message.setText(f'Cannot scan selection: {error}')
            self.start_button.setEnabled(True)
            return
        self.plan = plan
        self.message.setText(f'{len(plan.passwords)} comics to encrypt; {len(plan.skipped)} already encrypted; '
                             f'{len(plan.failed)} failures.'
                             + (' Cannot continue: one or more comics have no password configured in remoteConfig.ini.'
                                if plan.missing else ''))

    def _completed(self, result, error):
        if error:
            self.message.setText(f'Encryption failed: {error}')
            return
        prefix = 'Cancelled. ' if result['cancelled'] else ''
        self.message.setText(prefix + f"Encrypted: {len(result['encrypted'])}; skipped: {len(result['skipped'])}; failed: {len(result['failed'])}; not processed: {len(result['remaining'])}."
                             + ''.join(f'\n{path}: {message}' for path, message in result['failed'].items()))
        self.completed = True
        self.start_button.setText('Cancelled' if result['cancelled'] else 'Completed')

    def reject(self):
        if self.busy:
            self._cancel()
        else:
            super().reject()

    def closeEvent(self, event):
        if self.busy:
            self._cancel()
            event.ignore()
        else:
            super().closeEvent(event)
