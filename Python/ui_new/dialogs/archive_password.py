"""Password dialogs run only from explicit GUI actions, never archive workers."""

from commonUtils.ui import pyside as qt


def ask_password(path, message, parent=None):
    password, accepted = qt.QInputDialog.getText(parent, 'Unlock archive',
        f'{path.name}\n{message}\n\nPassword (kept only for this session):',
        qt.QLineEdit.EchoMode.Password)
    return password if accepted and password else None
