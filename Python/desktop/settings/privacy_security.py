"""Privacy & Security settings for Qt desktop."""
from commonUtils.ui import pyside as qt

from desktop.clipboard import CONFIG, FIELD
from features.settings import settings_store
from services.clipboard_policy import DESCRIPTION, LABEL


class PrivacyPanel(qt.QWidget):
    def __init__(self, parent=None, *, scope):
        super().__init__(parent)
        self.scope = scope
        self.store = settings_store(CONFIG)
        layout = qt.QVBoxLayout(self)
        self.choice = qt.QCheckBox(LABEL)
        description = qt.QLabel(DESCRIPTION + ' File Browser transfer commands remain available. '
                               'On X11, selection ownership is controlled separately.')
        description.setWordWrap(True)
        self.status = qt.QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.choice)
        layout.addWidget(description)
        layout.addWidget(self.status)
        layout.addStretch()
        self.reload()
        self.choice.toggled.connect(self.save)

    def set_scope(self, scope):
        self.scope = scope
        self.reload()

    def reload(self):
        with qt.QSignalBlocker(self.choice):
            self.choice.setChecked(self.store.safe_values(self.scope).get(FIELD, 'false').lower() == 'true')

    def save(self, enabled):
        try:
            self.store.save({FIELD: str(enabled).lower()}, scope=self.scope)
            self.status.clear()
        except (OSError, ValueError) as error:
            self.reload()
            self.status.setText(str(error))
