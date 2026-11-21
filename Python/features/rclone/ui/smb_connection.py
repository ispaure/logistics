"""Add or reconnect to an SMB server from desktop Workspaces."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.ui import pyside as qt
from commonUtils.ui.pyside.passwords import password_field
from commonUtils.ui.tasks.operation_progress import OperationProgress
from features.rclone.credential_loading import CredentialContext
from features.rclone.desktop_service import service
from features.rclone.desktop_smb import DesktopSMBLoad, ServerRecord, SMBEndpoint, SMBSecrets


class ServerConnectionDialog(qt.QDialog):
    def __init__(self, parent, record=None):
        super().__init__(parent)
        self.record = record
        self.adding = record is None
        self.saved = bool(record and record.encrypted)
        self.setWindowTitle('Add SMB server' if self.adding else 'Reconnect to SMB server')
        layout = qt.QVBoxLayout(self)
        title = qt.QLabel(
            'Connect to a Mac, PC, or NAS over SMB.' if self.adding else
            f'Reconnect to {record.name}.')
        title.setTextFormat(qt.Qt.TextFormat.PlainText)
        layout.addWidget(title)
        self.fields = qt.QWidget(self)
        layout.addWidget(self.fields)
        form = qt.QFormLayout(self.fields)

        if not self.saved:
            self.host = qt.QLineEdit(placeholderText='Hostname or IP address')
            self.user = qt.QLineEdit()
            self.password = qt.QLineEdit()
            password_field(self.password)
            self.domain = qt.QLineEdit('WORKGROUP')
            self.port = qt.QLineEdit('445')
            self.guest = qt.QCheckBox('Connect as guest')
            self.guest.toggled.connect(self._guest_changed)
            if self.adding:
                self.name = qt.QLineEdit()
                self.name.setMaxLength(80)
                form.addRow('Connection name', self.name)
            form.addRow('Server address', self.host)
            form.addRow(self.guest)
            form.addRow('Username', self.user)
            form.addRow('Password', self.password)
            form.addRow('Domain', self.domain)
            form.addRow('Port', self.port)
        self.remember = qt.QCheckBox('Save credentials on this device')
        if self.adding:
            form.addRow(self.remember)
        self.passphrase = qt.QLineEdit()
        password_field(self.passphrase)
        self.passphrase.setMaxLength(1024)
        self.passphrase.setPlaceholderText('At least 12 characters' if self.adding else '')
        form.addRow('Credential passphrase', self.passphrase)
        form.setRowVisible(self.passphrase, self.saved)
        if self.adding:
            self.confirmation = qt.QLineEdit()
            password_field(self.confirmation)
            self.confirmation.setMaxLength(1024)
            form.addRow('Confirm passphrase', self.confirmation)
            form.setRowVisible(self.confirmation, False)
            self.remember.toggled.connect(lambda enabled: form.setRowVisible(self.passphrase, enabled))
            self.remember.toggled.connect(lambda enabled: form.setRowVisible(self.confirmation, enabled))
            self.remember.toggled.connect(lambda enabled: self._clear_passphrase() if not enabled else None)
        saved_note = 'Saved credentials are encrypted with this passphrase. Keep it to reconnect.'
        session_note = 'Session-only connections ask for the server sign-in again after disconnecting or quitting.'
        note = qt.QLabel(saved_note if self.saved else session_note)
        self.remember.toggled.connect(lambda enabled: note.setText(saved_note if enabled else session_note))
        note.setWordWrap(True)
        layout.addWidget(note)
        self.error = qt.QLabel()
        self.error.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        self.operation = OperationProgress(self)
        self.operation.message.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.operation.completed.connect(self._finished)
        layout.addWidget(self.operation)
        buttons = qt.QDialogButtonBox(qt.QDialogButtonBox.StandardButton.Cancel)
        self.connect_button = buttons.addButton('Connect & browse', qt.QDialogButtonBox.ButtonRole.AcceptRole)
        self.connect_button.setDefault(True)
        buttons.accepted.connect(self.submit)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if self.saved:
            self.passphrase.setFocus()

    def _guest_changed(self, guest):
        self.password.clear()
        self.password.setEnabled(not guest)
        self.user.setEnabled(not guest)

    def _clear_passphrase(self):
        self.passphrase.clear()
        if self.adding:
            self.confirmation.clear()

    def submit(self):
        if self.operation.busy:
            return
        self.error.clear()
        try:
            record = ServerRecord.new(self.name.text().strip()) if self.adding else self.record
            account_password = ''
            endpoint = None
            remember = self.remember.isChecked()
            passphrase = self.passphrase.text()
            if remember and passphrase != self.confirmation.text():
                raise ValueError('The credential passphrases do not match.')
            if not self.saved:
                guest = self.guest.isChecked()
                endpoint = SMBEndpoint(self.host.text().strip(), 'guest' if guest else self.user.text().strip(),
                                       self.domain.text().strip(), self.port.text().strip())
                endpoint.settings()
                account_password = '' if guest else self.password.text()
                self.password.clear()
            self._clear_passphrase()
            from features.rclone.executable import ensure_rclone
            binary = ensure_rclone()
            if binary is None:
                raise ValueError('rclone is required to connect to an SMB server.')
        except (OSError, ValueError) as error:
            self.error.setText(str(error))
            return

        self.fields.setEnabled(False)
        self.connect_button.setEnabled(False)

        def prepare(_report, cancelled):
            request = DesktopSMBLoad(record, binary, endpoint, remember, self.adding, cancelled)
            return service.credentials.prepare_load(request, SMBSecrets(account_password, passphrase),
                                                    CredentialContext(cancelled))

        self.operation.start(prepare, message='Connecting to server…')

    def _finished(self, prepared, error):
        self.operation.hide()
        self.fields.setEnabled(True)
        self.connect_button.setEnabled(True)
        if self.operation.cancelled.is_set():
            service.credentials.discard(prepared)
            self.error.setText('Connection cancelled.')
        elif error:
            self.error.setText(error)
        else:
            try:
                result = service.credentials.unlock(prepared)
            except (OSError, ValueError) as error:
                self.error.setText(str(error))
            else:
                self.record = ServerRecord.new(result.remotes[0])
                self.accept()

    def reject(self):
        if self.operation.busy:
            self.operation.request_cancel()
            return
        self._clear_passphrase()
        if not self.saved:
            self.password.clear()
        super().reject()


class ServerReconnectView(qt.QWidget):
    idle = qt.Signal()

    def __init__(self, parent, record, reconnect):
        super().__init__(parent)
        layout = qt.QVBoxLayout(self)
        layout.addStretch()
        message = qt.QLabel(
            f'{record.name} is disconnected. Reconnect with your credential passphrase.'
            if record.encrypted else
            f'{record.name} is disconnected. Sign in again to unlock this session-only connection.')
        message.setTextFormat(qt.Qt.TextFormat.PlainText)
        message.setWordWrap(True)
        message.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(message)
        button = qt.QPushButton('Reconnect…')
        button.clicked.connect(reconnect)
        layout.addWidget(button, alignment=qt.Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()

    def prepare_close(self):
        return True
