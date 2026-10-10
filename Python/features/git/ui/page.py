"""Retained, dockable Git repository panes using the shared workspace."""
from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.ui.workspace import Workspace
from ..preferences import Preferences
from .repository_view import RepositoryView


class GitPage(qt.QWidget):
    idle = qt.Signal()

    def __init__(self, parent=None, *, preferences_path=None):
        super().__init__(parent)
        self.setProperty('navigation_position', 'workspace')
        self.setProperty('navigation_order', 20)
        self.preferences = Preferences(preferences_path)
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.workspace = Workspace(self._create_view, self, dock_group=self)
        layout.addWidget(self.workspace)
        self.workspace.add_view(self.preferences.last_repository or None)

    def _create_view(self, path):
        view = RepositoryView(preferences=self.preferences, repository_opener=self.open_repository,
                              restore_last=False)
        view.idle.connect(self.idle)
        if path is not None:
            view.open_repository(path)
        return view

    def open_repository(self, path):
        path = Path(path).expanduser().resolve()
        for dock in self.workspace.docks:
            view = dock.widget()
            if view.path == path or view.requested_path == path:
                dock.show(); dock.raise_()
                self.workspace._activate(dock)
                if view.path is None and not view.busy:
                    view.open_repository(path)
                return view
        current = self.workspace.active_view
        if current is not None and current.path is None and not current.busy and not current.requested_path:
            current.open_repository(path)
            return current
        return self.workspace.add_view(path)

    def can_close(self):
        return all(dock.widget().can_close() for dock in self.workspace.docks)

    def prepare_close(self):
        return self.workspace.prepare_close()
