"""Retained, dockable Git repository panes using the shared workspace."""
from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.ui.workspaces.workspace import Workspace
from commonUtils.ui.workspaces.workspace_policy import WorkspacePolicy
from ..preferences import Preferences
from .repository_view import RepositoryView


class GitPage(qt.QWidget):
    idle = qt.Signal()
    feature_settings_requested = qt.Signal(str)

    def __init__(self, parent=None, *, preferences_path=None):
        super().__init__(parent)
        self.setProperty('navigation_position', 'workspace')
        self.setProperty('navigation_order', 20)
        self.preferences = Preferences(preferences_path)
        self.working_file_opener = None
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.workspace = Workspace(self._create_view, self, dock_group=self, new_view=self._repository_menu,
            policy=WorkspacePolicy(show_single_tab_in_detached=False, detached_title='Git: {title}'))
        layout.addWidget(self.workspace)
        self.workspace.add_view((self.preferences.last_repository or None) if self.preferences.options['restore_windows'] else None)

    def _repository_menu(self, workspace):
        view = workspace.active_view
        if view is None and workspace.docks:
            view = workspace.docks[0].widget()
        if view is None:
            view = workspace.add_view()
        if not view.busy and not view.closing:
            view._repositories()
            view.repository_menu.popup(qt.QCursor.pos())

    def _create_view(self, path):
        view = RepositoryView(preferences=self.preferences, restore_last=False)
        view.working_file_opener = lambda path: bool(self.working_file_opener and self.working_file_opener(path))
        view.repository_opener = lambda path: self.open_repository(path, self._owner(view))
        view.menu_controls.menus['File'].addSeparator()
        view.menu_controls.add('File', 'Close Repository Tab', lambda: self._owner(view).close_active())
        view.idle.connect(self.idle)
        view.feature_settings_requested.connect(self.feature_settings_requested)
        if path is not None:
            view.open_repository(path)
        return view

    def _owner(self, view):
        return next((dock.workspace for dock in self.workspace.all_docks if dock.widget() is view), self.workspace)

    def open_repository(self, path, destination=None):
        path = Path(path).expanduser().resolve()
        destination = destination or self.workspace
        for dock in destination.docks:
            view = dock.widget()
            if view.path == path or view.requested_path == path:
                dock.show(); dock.raise_()
                destination._activate(dock)
                if view.path is None and not view.busy:
                    view.open_repository(path)
                return view
        current = destination.active_view
        if current is not None and current.path is None and not current.busy and not current.requested_path:
            current.open_repository(path)
            return current
        return destination.add_view(path)

    def can_close(self):
        return all(dock.widget().can_close() for dock in self.workspace.all_docks)

    def prepare_close(self):
        return self.workspace.prepare_close()
