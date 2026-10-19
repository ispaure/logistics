"""Resizable Workspaces panes with an opt-in native docking experiment."""
from commonUtils.ui import pyside as qt

# Set False (or pass panes_locked=False to FoldersPage) to try native docking.
WORKSPACE_PANES_LOCKED = True


class WorkspacePanes(qt.QMainWindow):
    def __init__(self, browser, actions, parent=None, *, locked=WORKSPACE_PANES_LOCKED):
        super().__init__(parent)
        self.setWindowFlags(qt.Qt.WindowType.Widget)
        self.setDockOptions(qt.QMainWindow.DockOption.AllowNestedDocks)
        self.docks = []
        for name, widget in (('Files', browser), ('Actions', actions)):
            dock = qt.QDockWidget(name, self)
            dock.setObjectName('workspaces.' + name.lower())
            dock.setWidget(widget)
            dock.setMinimumWidth(240)
            self.addDockWidget(qt.Qt.DockWidgetArea.LeftDockWidgetArea, dock)
            if self.docks:
                self.splitDockWidget(self.docks[-1], dock, qt.Qt.Orientation.Horizontal)
            self.docks.append(dock)
        self.set_locked(locked)
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
                header = qt.QTabBar(dock)
                header.addTab(dock.windowTitle())
                header.setExpanding(True)
                header.setMovable(False)
                header.setAccessibleName(dock.windowTitle() + ' pane (fixed)')
                dock.setTitleBarWidget(header)
            else:
                dock.setTitleBarWidget(None)
            if old is not None:
                old.deleteLater()
