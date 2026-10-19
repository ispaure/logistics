"""Application-session workspace visibility and its Settings panel."""
from commonUtils.ui import pyside as qt


class WorkspaceVisibility(qt.QObject):
    changed = qt.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.show_legacy = False

    def set_show_legacy(self, value):
        value = bool(value)
        if self.show_legacy != value:
            self.show_legacy = value
            self.changed.emit()


def workspace_visibility():
    app = qt.QApplication.instance()
    state = getattr(app, '_logistics_workspace_visibility', None)
    if state is None:
        state = WorkspaceVisibility(app)
        app._logistics_workspace_visibility = state
    return state


class WorkspaceSettingsPanel(qt.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.visibility = workspace_visibility()
        layout = qt.QVBoxLayout(self)
        self.show_legacy_choice = qt.QCheckBox('Show Legacy (session only)')
        self.show_legacy_choice.setChecked(self.visibility.show_legacy)
        self.show_legacy_choice.toggled.connect(self.visibility.set_show_legacy)
        self.visibility.changed.connect(self._sync)
        layout.addWidget(self.show_legacy_choice)
        description = qt.QLabel(
            'Show workspace names starting with Legacy- in Local, Cloud and Home Server. '
            'Hidden by default. This choice lasts only until the app closes.')
        description.setWordWrap(True)
        layout.addWidget(description)
        layout.addStretch()

    def _sync(self):
        with qt.QSignalBlocker(self.show_legacy_choice):
            self.show_legacy_choice.setChecked(self.visibility.show_legacy)
