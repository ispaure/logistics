"""Explicit desktop credential retention choice; publication remains service-owned."""
from commonUtils.ui import pyside as qt
from features.rclone.credential_storage import (
    SESSION_TITLE, SESSION_DESCRIPTION, PERSISTENT_TITLE, PERSISTENT_DESCRIPTION,
    SAVED_COPY_NOTE, SHARED_NOTE,
)


class CredentialUnlockDialog(qt.QDialog):
    def __init__(self, package, config_path, parent=None):
        super().__init__(parent)
        self.remember = None
        self.setWindowTitle('Unlock credential ZIP')
        self.setMinimumWidth(620)
        layout = qt.QVBoxLayout(self)
        title = qt.QLabel(f'How should Logistics keep credentials from {package.name}?')
        title.setTextFormat(qt.Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        layout.addWidget(title)
        options = qt.QHBoxLayout()
        self.session_button = self._option(options, SESSION_TITLE, SESSION_DESCRIPTION,
            'Unlock for this session', False)
        self.saved_button = self._option(options, PERSISTENT_TITLE, PERSISTENT_DESCRIPTION,
            'Unlock and save', True)
        layout.addLayout(options)
        if config_path.is_file():
            note = qt.QLabel(SAVED_COPY_NOTE)
            note.setWordWrap(True)
            layout.addWidget(note)
        note = qt.QLabel(SHARED_NOTE)
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = qt.QDialogButtonBox(qt.QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.session_button.setDefault(True)

    def _option(self, layout, title, description, button_text, remember):
        group = qt.QGroupBox(title)
        column = qt.QVBoxLayout(group)
        label = qt.QLabel(description)
        label.setWordWrap(True)
        column.addWidget(label)
        column.addStretch()
        button = qt.QPushButton(button_text)
        button.setAutoDefault(False)
        button.clicked.connect(lambda: self._choose(remember))
        column.addWidget(button)
        layout.addWidget(group, 1)
        return button

    def _choose(self, remember):
        self.remember = remember
        self.accept()


def choose_credential_retention(package, config_path, parent=None):
    dialog = CredentialUnlockDialog(package, config_path, parent)
    return dialog.remember if dialog.exec() == qt.QDialog.DialogCode.Accepted else None
