"""Resizable Workspaces panes with an opt-in native docking experiment."""
from commonUtils.ui import pyside as qt

# Set False (or pass panes_locked=False to FoldersPage) to try native docking.
WORKSPACE_PANES_LOCKED = True


class WorkspacePanes(qt.QMainWindow):
    def __init__(self, browser, actions, parent=None, *, sources=None, locked=WORKSPACE_PANES_LOCKED):
        super().__init__(parent)
        self.setWindowFlags(qt.Qt.WindowType.Widget)
        self.setDockOptions(qt.QMainWindow.DockOption.AllowNestedDocks)
        self.docks = []
        panes = [('Files', browser), ('Actions', actions)]
        if sources is not None:
            panes.append(('Sources', sources))
        for name, widget in panes:
            dock = qt.QDockWidget(name, self)
            dock.setObjectName('workspaces.' + name.lower())
            dock.setWidget(widget)
            dock.setMinimumWidth(240)
            if name != 'Sources':
                dock.setMinimumHeight(120)
            area = (qt.Qt.DockWidgetArea.RightDockWidgetArea if name == 'Files'
                    else qt.Qt.DockWidgetArea.LeftDockWidgetArea)
            self.addDockWidget(area, dock)
            self.docks.append(dock)
        self.set_locked(locked)
        if sources is not None:
            files, actions_dock, sources_dock = self.docks
            self.splitDockWidget(sources_dock, actions_dock, qt.Qt.Orientation.Vertical)
            self.resizeDocks([sources_dock, files], [300, 750], qt.Qt.Orientation.Horizontal)
            self.resizeDocks([sources_dock, actions_dock], [400, 250], qt.Qt.Orientation.Vertical)
        else:
            self.resizeDocks(self.docks, [650, 350], qt.Qt.Orientation.Horizontal)

    def createPopupMenu(self):
        return None

    def set_locked(self, locked):
        self.locked = bool(locked)
        for dock in self.docks:
            old = dock.titleBarWidget()
            dock.setFeatures(qt.QDockWidget.DockWidgetFeature.NoDockWidgetFeatures if locked else
                qt.QDockWidget.DockWidgetFeature.DockWidgetMovable | qt.QDockWidget.DockWidgetFeature.DockWidgetFloatable)
            if locked:
                header = qt.QWidget(dock)
                header.setFixedHeight(0)
                header.setAccessibleName(dock.windowTitle() + ' pane (fixed)')
                dock.setTitleBarWidget(header)
            else:
                dock.setTitleBarWidget(None)
            if old is not None:
                old.deleteLater()
