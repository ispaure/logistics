"""Logistics-owned password entry; passwords are never written to configuration."""
from commonUtils.ui import pyside as qt


def confirmed_password(parent, description):
    dialog = qt.QDialog(parent)
    dialog.setWindowTitle('Archive password')
    layout = qt.QVBoxLayout(dialog)
    label = qt.QLabel(description)
    label.setTextFormat(qt.Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    layout.addWidget(label)
    form = qt.QFormLayout()
    password = qt.QLineEdit()
    confirmation = qt.QLineEdit()
    for field in (password, confirmation):
        field.setEchoMode(qt.QLineEdit.EchoMode.Password)
    form.addRow('Password', password)
    form.addRow('Confirm password', confirmation)
    layout.addLayout(form)
    error = qt.QLabel()
    layout.addWidget(error)
    buttons = qt.QDialogButtonBox(qt.QDialogButtonBox.StandardButton.Ok | qt.QDialogButtonBox.StandardButton.Cancel)
    def accept():
        if not password.text():
            error.setText('Enter a nonempty password.')
        elif password.text() != confirmation.text():
            error.setText('Passwords do not match.')
        else:
            dialog.accept()
    buttons.accepted.connect(accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    try:
        return password.text() if dialog.exec() == qt.QDialog.DialogCode.Accepted else None
    finally:
        dialog.deleteLater()
