"""Explicit desktop credential retention choice; publication remains service-owned."""
from commonUtils.ui import pyside as qt


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
        self.session_button = self._option(options, 'Session only',
            'Keep unlocked credentials in memory until you lock them or exit Logistics. '
            'Only remote names and the ZIP location are remembered. Unlock the ZIP again next time; no passwords are saved. '
            'For crypt remotes, this also enables encrypted LocalCrypt copies.',
            'Unlock for this session', False)
        self.saved_button = self._option(options, 'Persistent — save on this device',
            'Save an rclone config so the remotes remain available after restarting Logistics. '
            'The saved config is not protected by the ZIP password. '
            'Use Forget Credentials to remove saved access.',
            'Unlock and save', True)
        layout.addLayout(options)
        if config_path.is_file():
            note = qt.QLabel('A saved config already exists for this package. Session only does not delete it. '
                            'Use Forget Credentials if you want to remove saved access.')
            note.setWordWrap(True)
            layout.addWidget(note)
        note = qt.QLabel('Both choices let you connect to Cloud. Your password-protected ZIP is kept in either case. '
                        'Pull reviews downloaded files separately; regular Local files remain readable after locking.')
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
