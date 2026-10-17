"""Password dialogs run only from explicit GUI actions, never archive workers."""

from commonUtils.ui import pyside as qt


def ask_password(path, message, parent=None, *, source=None):
    def validate(password):
        from contextlib import nullcontext
        from commonUtils.archives.zip_access import authenticate
        cancelled = dialog.operation.cancelled.is_set
        if source is None:
            authenticate(path, password, cancelled=cancelled)
            from services.documents.zip_passwords import remember_verified_password
            remember_verified_password(path, password)
        else:
            scope = getattr(source, 'operation', None)
            with scope(cancelled) if scope else nullcontext():
                with source.open(path) as stream:
                    authenticate(stream, password, cancelled=cancelled)
        return password
    dialog = ValidatedPasswordDialog(path, message, validate, parent, title='Unlock archive',
        error_message='Incorrect password or unreadable archive. Please try again.')
    try:
        return dialog.result_value if dialog.exec() == qt.QDialog.DialogCode.Accepted else None
    finally:
        dialog.deleteLater()


class ValidatedPasswordDialog(qt.QDialog):
    """Keep the same prompt open until validation succeeds or the user cancels."""
    def __init__(self, path, message, validate, parent=None, *, title='Unlock credentials',
                 error_message='Incorrect password or invalid credential ZIP. Please try again.'):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.error_message = error_message
        self.validate = validate
        self.result_value = None
        self.pending_cancel = False
        layout = qt.QVBoxLayout(self)
        label = qt.QLabel(f'{path.name}\n{message}')
        label.setTextFormat(qt.Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.password = qt.QLineEdit(self)
        self.password.setEchoMode(qt.QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText('Password')
        self.password.setAccessibleName('Archive password' if title == 'Unlock archive' else 'Credential ZIP password')
        self.password.installEventFilter(self)
        layout.addWidget(self.password)
        self.error = qt.QLabel(self)
        self.error.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        from commonUtils.ui.tasks.operation_progress import OperationProgress
        self.operation = OperationProgress(self)
        self.operation.completed.connect(self._validated)
        layout.addWidget(self.operation)
        self.buttons = qt.QDialogButtonBox(qt.QDialogButtonBox.StandardButton.Ok | qt.QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.submit)
        self.buttons.rejected.connect(self.reject)
        for button in self.buttons.buttons():
            button.setAutoDefault(False)
            button.setDefault(False)
        self.operation.cancel_button.setAutoDefault(False)
        layout.addWidget(self.buttons)
        self.password.setFocus()

    def eventFilter(self, watched, event):
        if watched is self.password and event.type() == qt.QEvent.Type.KeyPress and event.key() in (qt.Qt.Key.Key_Return, qt.Qt.Key.Key_Enter):
            self.submit()
            event.accept()
            return True
        return super().eventFilter(watched, event)

    def submit(self):
        if self.operation.busy or not self.password.text():
            return
        password = self.password.text()
        self.password.clear()
        self.password.setEnabled(False)
        self.buttons.button(qt.QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.error.clear()
        def validate(report, cancelled):
            try:
                return self.validate(password)
            except Exception:
                raise ValueError(self.error_message) from None
        self.operation.start(validate, message='Unlocking credentials…')

    def _validated(self, result, error):
        self.operation.hide()
        if self.pending_cancel or self.operation.cancelled.is_set():
            self.pending_cancel = False
            super().reject()
        elif error:
            self.error.setText(error)
            self.password.setEnabled(True)
            self.password.clear()
            self.password.setFocus(qt.Qt.FocusReason.OtherFocusReason)
            self.buttons.button(qt.QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        else:
            self.result_value = result
            self.accept()

    def reject(self):
        if self.operation.busy:
            self.pending_cancel = True
            self.operation.request_cancel()
            return
        self.password.clear()
        super().reject()

    def closeEvent(self, event):
        if self.operation.busy:
            self.reject()
            event.ignore()
        else:
            self.password.clear()
            event.accept()


def ask_validated_password(path, message, validate, parent=None):
    dialog = ValidatedPasswordDialog(path, message, validate, parent)
    try:
        return dialog.result_value if dialog.exec() == qt.QDialog.DialogCode.Accepted else None
    finally:
        dialog.deleteLater()
