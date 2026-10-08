"""Create a separate AES-256 ZIP from an existing browser selection."""

import os
from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.ui.operation_progress import OperationProgress
from commonUtils.operations import OperationCancelled
from commonUtils.zip_access import create_archive, password_bytes
from services.zip_passwords import configured_password
from services.password_prompt import confirmed_password


class CreateZipDialog(qt.QDialog):
    def __init__(self, targets, parent=None):
        super().__init__(parent)
        self.targets = tuple(dict.fromkeys(Path(path).absolute() for path in targets))
        self.busy = False
        self.succeeded = False
        self.task = OperationProgress(self)
        self.task.cancel_button.hide()
        self.task.completed.connect(self._completed)
        self.setWindowTitle('Create encrypted ZIP')
        layout = qt.QVBoxLayout(self)
        self.summary = qt.QLabel('\n'.join(str(path) for path in self.targets))
        self.summary.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        description = qt.QLabel('Creates a separate AES-256 ZIP using the configured archive password. '
                                'Sources are kept. Filenames inside ZIP remain visible without a password.')
        description.setWordWrap(True)
        layout.addWidget(description)
        folder = Path(os.path.commonpath([str(path.parent) for path in self.targets]))
        name = (self.targets[0].name if self.targets[0].is_dir() else self.targets[0].stem) if len(self.targets) == 1 else 'Selection'
        self.output = qt.QLineEdit(str(folder / (name + '.zip')))
        row = qt.QHBoxLayout()
        row.addWidget(self.output)
        self.browse = qt.QPushButton('Browse…')
        self.browse.clicked.connect(self._browse)
        row.addWidget(self.browse)
        layout.addLayout(row)
        self.message = qt.QLabel()
        self.message.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        layout.addWidget(self.task)
        buttons = qt.QHBoxLayout()
        self.create_button = qt.QPushButton('Create encrypted ZIP')
        self.cancel_button = qt.QPushButton('Cancel')
        self.create_button.clicked.connect(self._create)
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.create_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)
        self.resize(600, 260)

    def _browse(self):
        path, _ = qt.QFileDialog.getSaveFileName(self, 'Encrypted ZIP destination', self.output.text(), 'ZIP archives (*.zip)')
        if path:
            self.output.setText(path)

    def _create(self):
        if self.busy:
            return
        destination = Path(self.output.text())
        try:
            passwords = [configured_password(path) for path in self.targets]
            configured = {password_bytes(password) for password in passwords if password}
            if len(configured) > 1:
                raise ValueError('Selected items use different configured passwords; create separate ZIPs.')
            password = next(iter(configured), None)
            if any(not value for value in passwords):
                password = confirmed_password(self, 'This password will protect the new ZIP. It is not saved to remoteConfig.ini.')
                if password is None:
                    return
                if configured and password_bytes(password) not in configured:
                    raise ValueError('The entered password differs from the configured password; create separate ZIPs.')
        except (OSError, ValueError) as error:
            self.message.setText(f'ZIP was not created: {error}')
            return
        targets = self.targets
        def create(progress, cancelled):
            try:
                return create_archive(targets, destination, password=password,
                                      progress=progress, cancelled=cancelled)
            except OperationCancelled:
                return None
        self.busy = True
        self.message.setText('Creating and verifying encrypted ZIP…')
        for widget in (self.create_button, self.output, self.browse):
            widget.setEnabled(False)
        self.cancel_button.setText('Cancel ZIP creation')
        self.task.start(create, message='Assessing selected files…',
                        cancel_message='Cancelling ZIP creation and discarding temporary output…')

    def _completed(self, result, error):
        self.busy = False
        self.succeeded = not error and result is not None
        if error:
            self.message.setText(f'ZIP was not created: {error}')
        elif result is None:
            self.message.setText('Cancelled. ZIP was not created; sources are unchanged.')
        else:
            self.message.setText(f'Created {result}')
        for widget in (self.create_button, self.cancel_button, self.output, self.browse):
            widget.setEnabled(True)
        self.cancel_button.setText('Close')
        if self.succeeded:
            self.accept()

    def reject(self):
        if self.busy:
            self.task.request_cancel()
            self.cancel_button.setEnabled(False)
        else:
            super().reject()

    def closeEvent(self, event):
        if self.busy:
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)
