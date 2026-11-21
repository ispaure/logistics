"""Spring-loaded destinations for Logistics File Browser drags."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import os
from pathlib import Path
from weakref import WeakSet
from shiboken6 import isValid

from commonUtils.filesystem.local_access import check_local_path
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser.drag_drop import MIME, SESSION
from commonUtils.ui.workspaces.workspace import WorkspaceDock
from .browser_moves import MoveSource, PrivateMoveMime
from .native_file_drag import LocalFileDrag, handoff_message, local_drag_paths, native_drop_action, start_file_drag


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
            for path in paths:
                check_local_path(path, recursive=True)
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

    def start_drag(self, widget, moves, view, event):
        if not self.press:
            return False
        viewport, origin = self.press
        if viewport is not widget or (event.position().toPoint() - origin).manhattanLength() < qt.QApplication.startDragDistance():
            return False
        self.press = None
        # The common browser has its own fallback gesture. Once Logistics has
        # consumed this press, the fallback must not publish unguarded URLs.
        actions = getattr(moves.browser, 'file_actions', None)
        if actions is not None:
            actions.drag_drop.press = None
        if not moves.available():
            return True
        if not view.indexAt(origin).isValid():
            return False
        if getattr(moves.host, 'provider', None) is None:
            browser = moves.browser
            selection = view.selectionModel()
            indices = selection.selectedRows(0) or selection.selectedIndexes()
            names = (browser.model.filePath(browser.views.source_index(index))
                     for index in indices if index.column() == 0)
            paths = tuple(dict.fromkeys(Path(name) for name in names if name and Path(name).is_absolute()))
            if not paths:
                return False
            try:
                action = start_file_drag(view, paths, internal=True)
                moves.handoff(handoff_message(action))
            except (OSError, ValueError) as error:
                moves.handoff(str(error))
            finally:
                self.clear()
            return True
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
            if moves is not None:
                left = qt.Qt.MouseButton.LeftButton
                if kind == qt.QEvent.Type.MouseButtonPress:
                    self.press = (widget, event.position().toPoint()) if event.button() == left else None
                elif kind == qt.QEvent.Type.MouseButtonRelease:
                    self.press = None
                elif kind == qt.QEvent.Type.MouseMove and event.buttons() & left:
                    return self.start_drag(widget, moves, view, event)
            return False
        if kind not in (qt.QEvent.Type.DragEnter, qt.QEvent.Type.DragMove, qt.QEvent.Type.Drop):
            return False
        mime = event.mimeData()
        sources = mime.sources if isinstance(mime, PrivateMoveMime) else ()
        internal = bool(sources) or bytes(mime.data(MIME)) == SESSION
        paths = () if sources else local_drag_paths(mime)
        if not sources and not paths and not mime.hasUrls():
            return False
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
            return self.drop_event(event, widget, moves, directory, sources, paths, internal, rect, dock, open_target)
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
        return self.drop_event(event, widget, moves, directory, sources, paths, internal, rect, directory, opener)

    def drop_event(self, event, widget, moves, directory, sources, paths, internal, rect, key, open_target):
        modifiers = qt.Qt.KeyboardModifier.ControlModifier | qt.Qt.KeyboardModifier.AltModifier
        actions = qt.Qt.DropAction
        protected = moves is not None and getattr(moves.host, 'provider', None) is not None
        if (not (paths or sources) or not self.available(moves, directory, paths, sources)):
            self.clear(widget)
            event.ignore()
            return True
        if internal:
            action = actions.CopyAction if event.modifiers() & modifiers else actions.MoveAction
        else:
            action = native_drop_action(event, paths, directory, protected=protected)
        copy = action == actions.CopyAction
        if (action == actions.IgnoreAction or not event.possibleActions() & action
                or internal and copy and (sources or protected)
                or not internal and not event.possibleActions() & actions.CopyAction):
            self.clear(widget)
            event.ignore()
            return True
        # A native source must never interpret acceptance as permission to
        # delete anything before our worker has published and verified it.
        event.setDropAction(action if internal else actions.CopyAction)
        event.accept()
        if event.type() == qt.QEvent.Type.Drop:
            self.clear()
            mime = event.mimeData()
            if isinstance(mime, LocalFileDrag):
                mime.handled = True
            if copy and internal:
                moves.browser.file_actions.transfer(paths, directory)
            else:
                # Return from the native drag before asking about decrypted output.
                def apply():
                    try:
                        started = moves.start(sources or tuple(MoveSource.local(path) for path in paths), directory,
                                              native=not internal, copy=copy)
                        if not started and not internal:
                            moves.handoff('The destination became unavailable before the transfer started.')
                    except (OSError, ValueError) as error:
                        qt.QMessageBox.warning(moves.host, 'File transfer', str(error))
                qt.QTimer.singleShot(0, moves, apply)
        else:
            self.hover(widget, key, rect, open_target)
        return True
