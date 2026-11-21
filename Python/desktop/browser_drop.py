"""Spring-loaded destinations for Logistics File Browser drags."""
import os
from pathlib import Path
from weakref import WeakSet
from shiboken6 import isValid

from commonUtils.filesystem.local_access import check_local_path
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser.drag_drop import MIME, SESSION
from commonUtils.ui.workspaces.workspace import WorkspaceDock
from .browser_moves import MoveSource, PrivateMoveMime


class BrowserDropTargets(qt.QObject):
    def __init__(self, app):
        super().__init__(app)
        self.workspaces = WeakSet()
        self.timer = qt.QTimer(self)
        self.timer.setInterval(130)
        self.timer.timeout.connect(self.advance)
        self.target = self.band = None
        self.press = None
        app.installEventFilter(self)

    @classmethod
    def instance(cls):
        app = qt.QApplication.instance()
        controller = getattr(app, '_logistics_browser_drop_targets', None)
        if controller is None:
            controller = app._logistics_browser_drop_targets = cls(app)
        return controller

    @classmethod
    def register(cls, workspace):
        controller = cls.instance()
        controller.workspaces.add(workspace)
        return controller

    def clear(self, widget=None):
        if self.target is None or widget is not None and self.target[0] is not widget:
            return
        self.timer.stop()
        self.target = None
        if self.band is not None:
            if isValid(self.band):
                self.band.hide()
                self.band.deleteLater()
            self.band = None

    def hover(self, widget, key, rect, open_target):
        if self.target is not None and self.target[:2] == (widget, key):
            if self.band is not None:
                self.band.setGeometry(rect)
            return
        self.clear()
        self.target = widget, key, open_target
        self.band = qt.QRubberBand(qt.QRubberBand.Shape.Rectangle, widget)
        self.band.setGeometry(rect)
        self.band.show()
        self.pulse_tick = 0
        if open_target is not None:
            self.timer.start()

    def advance(self):
        if self.target is None:
            return
        widget, _, open_target = self.target
        if not isValid(widget):
            self.timer.stop()
            self.target = self.band = None
            return
        if not widget.isVisible():
            self.clear()
            return
        self.pulse_tick += 1
        if self.pulse_tick == 5:
            self.timer.stop()
            self.band.hide()
            open_target()
        else:
            self.band.setVisible(self.pulse_tick % 2 == 0)

    @staticmethod
    def view_target(widget):
        view = widget.parentWidget()
        if not isinstance(view, qt.QAbstractItemView) or view.viewport() is not widget:
            return None, None
        parent = view.parentWidget()
        while parent is not None:
            moves = getattr(parent, 'move_actions', None)
            if moves is not None:
                browser = moves.browser
                actions = getattr(browser, 'file_actions', None)
                if actions is not None:
                    return (moves, view) if widget in actions.drag_drop.views else (None, None)
                views = browser.views
                if view in views.navigation_views or views.columns is not None and views.columns.isAncestorOf(view):
                    return moves, view
                return None, None
            parent = parent.parentWidget()
        return None, None

    @staticmethod
    def available(moves, directory, paths, sources):
        if moves is None or directory is None or not moves.available():
            return False
        provider = getattr(moves.host, 'provider', None)
        try:
            if provider is not None:
                folder = provider.relative(directory)
                return not any(item.provider.storage_namespace == provider.storage_namespace
                               and item.provider.storage_id == provider.storage_id
                               and (folder == item.path or folder.startswith(item.path + '/')) for item in sources)
            if not directory.is_dir() or not os.access(directory, os.W_OK | os.X_OK):
                return False
            check_local_path(directory)
            target = directory.resolve()
            return all(path.is_symlink() or (path.resolve() != target and path.resolve() not in target.parents)
                       for path in paths)
        except (OSError, ValueError):
            return False

    def start_private_drag(self, widget, moves, view, event):
        if not moves.host.isEnabled() or moves.busy or moves.browser.busy or not self.press:
            return False
        viewport, origin = self.press
        if viewport is not widget or (event.position().toPoint() - origin).manhattanLength() < qt.QApplication.startDragDistance():
            return False
        self.press = None
        if not view.indexAt(origin).isValid():
            return False
        sources = moves.selected_sources()
        if not sources:
            return False
        drag = qt.QDrag(view)
        mime = PrivateMoveMime(sources)
        drag.setMimeData(mime)
        try:
            drag.exec(qt.Qt.DropAction.MoveAction)
        finally:
            mime.sources = ()
            self.clear()
            drag.deleteLater()
        return True

    def eventFilter(self, widget, event):
        kind = event.type()
        if kind == qt.QEvent.Type.KeyPress and event.key() == qt.Qt.Key.Key_Escape:
            self.clear()
        if kind in (qt.QEvent.Type.DragLeave, qt.QEvent.Type.Hide):
            self.clear(widget)
            return False
        if not isinstance(widget, qt.QWidget):
            return False
        bar = isinstance(widget, qt.QTabBar)
        workspace = widget.parent() if bar else None
        if kind == qt.QEvent.Type.Show:
            if bar and workspace in self.workspaces:
                widget.setAcceptDrops(True)
            moves, view = self.view_target(widget)
            if moves is not None and getattr(moves.host, 'provider', None) is not None:
                widget.setAcceptDrops(True)
                view.setDragEnabled(False)
            return False
        if kind in (qt.QEvent.Type.MouseButtonPress, qt.QEvent.Type.MouseButtonRelease, qt.QEvent.Type.MouseMove):
            moves, view = self.view_target(widget)
            if moves is not None and getattr(moves.host, 'provider', None) is not None:
                left = qt.Qt.MouseButton.LeftButton
                if kind == qt.QEvent.Type.MouseButtonPress and event.button() == left:
                    self.press = widget, event.position().toPoint()
                elif kind == qt.QEvent.Type.MouseButtonRelease:
                    self.press = None
                elif kind == qt.QEvent.Type.MouseMove and event.buttons() & left:
                    return self.start_private_drag(widget, moves, view, event)
            return False
        if kind not in (qt.QEvent.Type.DragEnter, qt.QEvent.Type.DragMove, qt.QEvent.Type.Drop):
            return False
        mime = event.mimeData()
        sources = mime.sources if isinstance(mime, PrivateMoveMime) else ()
        paths = ()
        if not sources:
            if bytes(mime.data(MIME)) != SESSION:
                return False
            urls = mime.urls()
            if not urls or any(not url.isLocalFile() for url in urls):
                return False
            paths = tuple(Path(url.toLocalFile()) for url in urls)
        point = event.position().toPoint()
        dock = None
        if bar and workspace in self.workspaces:
            index = widget.tabAt(point)
            dock = workspace._tab_dock(widget, index) if index >= 0 else None
        elif isinstance(widget, WorkspaceDock) and widget.workspace in self.workspaces:
            dock, workspace = widget, widget.workspace
        if (bar and workspace in self.workspaces) or dock is not None:
            moves = getattr(dock.widget(), 'move_actions', None) if dock is not None else None
            directory = moves.browser.navigation.directory if moves is not None else None
            rect = widget.tabRect(index) if bar and dock is not None else widget.rect()
            def open_target():
                if dock in workspace.docks:
                    dock.raise_()
                    workspace._activate(dock)
            return self.drop_event(event, widget, moves, directory, sources, paths, rect, dock, open_target)
        moves, view = self.view_target(widget)
        if moves is None:
            return False
        browser = moves.browser
        index = view.indexAt(point)
        index_source = browser.views.source_index(index)
        if hasattr(browser, 'file_actions'):
            drag = browser.file_actions.drag_drop
            drag.indicators[widget].hide()
            directory = drag.destination(view, point)
            on_folder = index_source.isValid() and browser.model.isDir(index_source)
        else:
            row = index_source.data(qt.Qt.ItemDataRole.UserRole) if index_source.isValid() else None
            on_folder = row is not None and row['directory']
            directory = moves.host.provider.root / row['path'] if on_folder else browser.navigation.directory
        rect = view.visualRect(index) if on_folder else widget.rect()
        opener = (lambda: browser.navigate(directory)) if on_folder else None
        return self.drop_event(event, widget, moves, directory, sources, paths, rect, directory, opener)

    def drop_event(self, event, widget, moves, directory, sources, paths, rect, key, open_target):
        modifiers = qt.Qt.KeyboardModifier.ControlModifier | qt.Qt.KeyboardModifier.AltModifier
        copy = bool(event.modifiers() & modifiers)
        private = bool(sources) or moves is not None and getattr(moves.host, 'provider', None) is not None
        action = qt.Qt.DropAction.CopyAction if copy else qt.Qt.DropAction.MoveAction
        if (not self.available(moves, directory, paths, sources) or copy and private
                or not event.possibleActions() & action):
            self.clear(widget)
            event.ignore()
            return True
        event.setDropAction(action)
        event.accept()
        if event.type() == qt.QEvent.Type.Drop:
            self.clear()
            if copy:
                moves.browser.file_actions.transfer(paths, directory)
            else:
                # Return from the native drag before asking about decrypted output.
                def apply():
                    try:
                        moves.start(sources or tuple(MoveSource.local(path) for path in paths), directory)
                    except (OSError, ValueError) as error:
                        qt.QMessageBox.warning(moves.host, 'Cannot move files', str(error))
                qt.QTimer.singleShot(0, moves, apply)
        else:
            self.hover(widget, key, rect, open_target)
        return True
