"""Inline credential unlock for the desktop Workspaces Files pane."""
from pathlib import Path

from commonUtils.ui import pyside as qt
from commonUtils.ui.pyside.passwords import password_field
from commonUtils.ui.tasks.operation_progress import OperationProgress
from features.rclone import session


def unlock_target(location, *, package=None):
    from desktop.file_browser import _PrivateBrowserLocation
    from features.rclone.ui.remote_browser import RemoteLocation
    if isinstance(location, _PrivateBrowserLocation):
        config, package = Path(location.item.context), Path(location.item.package)
    elif isinstance(location, RemoteLocation):
        config = Path(location.config)
        package = Path(package) if package is not None else session.package_path(config)
    else:
        return None
    if config.suffix != '.session':
        return None
    if session.credentials(config) is not None and (package is None or session.package_path(config) == package):
        return None
    return config, package


class WorkspaceUnlockView(qt.QWidget):
    idle = qt.Signal()
    unlocked = qt.Signal()

    def __init__(self, config, package, parent=None, *, purpose='browse this folder', workspace_name=None):
        super().__init__(parent)
        self.config, self.package, self.closing = config, package, False
        layout = qt.QVBoxLayout(self)
        layout.addStretch()
        form = qt.QWidget(self)
        form.setMaximumWidth(360)
        fields = qt.QVBoxLayout(form)
        if workspace_name:
            name = qt.QLabel(workspace_name)
            name.setTextFormat(qt.Qt.TextFormat.PlainText)
            name.setWordWrap(True)
            name.setAccessibleName('Selected workspace')
            fields.addWidget(name)
        title = qt.QLabel('Unlock this workspace')
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        fields.addWidget(title)
        message = qt.QLabel(
            f'Enter the password for {package.name} to {purpose}. Credentials stay in this app session.'
            if package else 'Unlock the matching credential ZIP in Settings, then choose Try again.')
        message.setTextFormat(qt.Qt.TextFormat.PlainText)
        message.setWordWrap(True)
        fields.addWidget(message)
        self.password = qt.QLineEdit(self)
        password_field(self.password)
        self.password.setPlaceholderText('Credential ZIP password')
        self.password.setAccessibleName('Credential ZIP password')
        fields.addWidget(self.password)
        self.error = qt.QLabel(self)
        self.error.setWordWrap(True)
        self.error.setTextFormat(qt.Qt.TextFormat.PlainText)
        fields.addWidget(self.error)
        self.error.hide()
        self.submit_button = qt.QPushButton('Unlock' if package else 'Try again', self)
        fields.addWidget(self.submit_button)
        self.operation = OperationProgress(self)
        self.operation.completed.connect(self._completed)
        fields.addWidget(self.operation)
        self.submit_button.clicked.connect(self.submit)
        self.password.returnPressed.connect(self.submit)
        self.password.setVisible(package is not None)
        row = qt.QHBoxLayout()
        row.addStretch(1)
        row.addWidget(form, 4)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch()

    def submit(self):
        if self.closing or self.operation.busy:
            return
        if self.package is None:
            self.unlocked.emit()
            return
        if not self.password.text():
            return
        password = self.password.text()
        self.password.clear()
        self.password.setEnabled(False)
        self.submit_button.setEnabled(False)
        self.error.clear()
        self.error.hide()
        package = self.package
        def validate(report, cancelled):
            try:
                return session.read_package(package, password)
            except Exception:
                raise ValueError('Could not unlock the credential ZIP.') from None
        self.operation.start(validate, message='Unlocking credentials…')

    def _completed(self, values, error):
        self.operation.hide()
        if self.closing:
            self.idle.emit()
            return
        self.error.setVisible(bool(error) or self.operation.cancelled.is_set())
        self.password.setEnabled(True)
        self.submit_button.setEnabled(True)
        if self.operation.cancelled.is_set():
            self.error.setText('Unlock cancelled.')
        elif error:
            self.error.setText('Could not unlock the credential ZIP. Check the password and try again.')
        else:
            session.remember(self.config, values, package_path=self.package)
            self.unlocked.emit()
        self.idle.emit()

    def prepare_close(self):
        self.closing = True
        self.password.clear()
        self.operation.request_cancel()
        return not self.operation.busy
