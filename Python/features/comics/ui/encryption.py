"""Plan once, prompt once for missing passwords, then encrypt a fixed selection."""
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser.operations import Operation
from services.password_prompt import confirmed_password
from features.comics.encryption import plan_encryption, execute_encryption


class EncryptComicsDialog(qt.QDialog):
    def __init__(self, targets, parent=None):
        super().__init__(parent)
        self.targets = tuple(targets)
        self.busy = False
        self.plan = None
        self.completed = False
        self.setWindowTitle('Encrypt unencrypted comics')
        layout = qt.QVBoxLayout(self)
        description = qt.QLabel('Encrypt unencrypted CBZ files in the selection, including nested folders. '
                               'Existing encrypted comics are skipped. Names and file contents are preserved. '
                               'Each comic uses its configured password; one confirmed password covers all comics without one.')
        description.setWordWrap(True)
        layout.addWidget(description)
        self.message = qt.QLabel()
        self.message.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.start_button = qt.QPushButton('Check selected comics')
        self.start_button.clicked.connect(self._start)
        layout.addWidget(self.start_button)
        self.resize(600, 260)

    def _run(self, work, completed):
        self.busy = True
        self.start_button.setEnabled(False)
        operation = Operation(work, self)
        self.operation = operation
        operation.completed.connect(completed)
        operation.finished.connect(lambda: self._finished(operation))
        operation.start()

    def _finished(self, operation):
        self.busy = False
        operation.deleteLater()
        if not self.completed:
            self.start_button.setText('Encrypt comics' if self.plan is not None else 'Check selected comics')
            self.start_button.setEnabled(True)

    def _start(self):
        if self.busy or self.completed:
            return
        if self.plan is None:
            self.message.setText('Checking selected comics…')
            self._run(lambda: plan_encryption(self.targets), self._planned)
        else:
            fallback = None
            if self.plan.missing:
                fallback = confirmed_password(self, f'One password will be used for all {len(self.plan.missing)} comics '
                                              'without a configured INI password in this operation. Enter it twice to confirm. '
                                              'It will not be saved to remoteConfig.ini.')
                if fallback is None:
                    return
            plan = self.plan
            self.plan = None
            self.message.setText('Encrypting and verifying comics…')
            self._run(lambda: execute_encryption(plan, fallback), self._completed)

    def _planned(self, plan, error):
        if error:
            self.message.setText(f'Cannot scan selection: {error}')
            self.start_button.setEnabled(True)
            return
        self.plan = plan
        self.message.setText(f'{len(plan.passwords)} comics to encrypt; {len(plan.skipped)} already encrypted; '
                             f'{len(plan.failed)} failures. {len(plan.missing)} comics need the shared password.')

    def _completed(self, result, error):
        if error:
            self.message.setText(f'Encryption failed: {error}')
            return
        self.message.setText(f"Encrypted: {len(result['encrypted'])}; skipped: {len(result['skipped'])}; failed: {len(result['failed'])}."
                             + ''.join(f'\n{path}: {message}' for path, message in result['failed'].items()))
        self.completed = True
        self.start_button.setText('Completed')

    def reject(self):
        if not self.busy:
            super().reject()

    def closeEvent(self, event):
        if self.busy:
            event.ignore()
        else:
            super().closeEvent(event)
