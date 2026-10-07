"""Create a separate AES-256 ZIP from an existing browser selection."""

import os
from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser.operations import Operation
from commonUtils.zip_access import create_archive, password_bytes
from services.zip_passwords import configured_password


class CreateZipDialog(qt.QDialog):
    def __init__(self, targets, parent=None):
        super().__init__(parent)
        self.targets = tuple(dict.fromkeys(Path(path).absolute() for path in targets))
        self.busy = False
        self.operation = None
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
        name = self.targets[0].name if len(self.targets) == 1 else 'Selection'
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
        def create():
            passwords = [configured_password(path) for path in self.targets]
            if any(not password for password in passwords):
                raise ValueError('Every selected item needs a nonempty [LogisticsZIP] archive_password in its configuration.')
            if len({password_bytes(password) for password in passwords}) != 1:
                raise ValueError('Selected items use different configured passwords; create separate ZIPs.')
            return create_archive(self.targets, destination, password=passwords[0])
        self.busy = True
        self.message.setText('Creating and verifying encrypted ZIP…')
        for widget in (self.create_button, self.cancel_button, self.output, self.browse):
            widget.setEnabled(False)
        self.operation = Operation(create, self)
        self.operation.completed.connect(self._completed)
        self.operation.finished.connect(self._finished)
        self.operation.start()

    def _completed(self, result, error):
        self.message.setText(f'ZIP was not created: {error}' if error else f'Created {result}')
        self.succeeded = not error

    def _finished(self):
        self.busy = False
        self.operation.deleteLater()
        for widget in (self.create_button, self.cancel_button, self.output, self.browse):
            widget.setEnabled(True)
        if self.succeeded:
            self.accept()

    def reject(self):
        if not self.busy:
            super().reject()

    def closeEvent(self, event):
        if self.busy:
            event.ignore()
        else:
            super().closeEvent(event)
