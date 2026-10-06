"""Shared filesystem list, tile and column views with asynchronous cover icons."""

from collections import deque, OrderedDict
from pathlib import Path
from commonUtils.ui import pyside as qt
from features.comics.pages import ComicPages
from .operations import Operation


class CoverModel(qt.QIdentityProxyModel):
    cover_requested = qt.Signal(str)

    def __init__(self, source, parent=None):
        super().__init__(parent)
        self.setSourceModel(source)
        self.icons = OrderedDict()
        self.requested = set()
        self.revisions = {}

    def data(self, index, role=qt.Qt.ItemDataRole.DisplayRole):
        if role == qt.Qt.ItemDataRole.DecorationRole and index.column() == 0:
            source = self.mapToSource(index)
            path = self.sourceModel().filePath(source)
            if path.lower().endswith('.cbz') and not self.sourceModel().isDir(source):
                if path in self.icons:
                    self.icons.move_to_end(path)
                    return self.icons[path]
                if path not in self.requested:
                    self.requested.add(path)
                    self.cover_requested.emit(path)
        value = super().data(index, role)
        if role == qt.Qt.ItemDataRole.DecorationRole and index.column() == 0 and (value is None or value.isNull()):
            source = self.mapToSource(index)
            kind = qt.QStyle.StandardPixmap.SP_DirIcon if self.sourceModel().isDir(source) else qt.QStyle.StandardPixmap.SP_FileIcon
            return qt.QApplication.style().standardIcon(kind)
        return value

    def complete(self, path, data):
        source = self.sourceModel().index(path)
        pixmap = qt.QPixmap()
        pixmap.loadFromData(data)
        icon = qt.QIcon(pixmap) if not pixmap.isNull() else self.sourceModel().data(source, qt.Qt.ItemDataRole.DecorationRole)
        if icon is None or icon.isNull():
            icon = qt.QApplication.style().standardIcon(qt.QStyle.StandardPixmap.SP_FileIcon)
        self.icons[path] = icon
        self.icons.move_to_end(path)
        while len(self.icons) > 128:
            evicted, _ = self.icons.popitem(last=False)
            self.requested.discard(evicted)
        index = self.mapFromSource(source)
        if index.isValid():
            self.dataChanged.emit(index, index, [qt.Qt.ItemDataRole.DecorationRole])

    def invalidate(self, path):
        path = str(path)
        self.revisions[path] = self.revisions.get(path, 0) + 1
        self.icons.pop(path, None)
        self.requested.discard(path)
        index = self.mapFromSource(self.sourceModel().index(path))
        if index.isValid():
            self.dataChanged.emit(index, index, [qt.Qt.ItemDataRole.DecorationRole])


class FileBrowser(qt.QStackedWidget):
    selection_changed = qt.Signal()
    context_requested = qt.Signal(object)
    activated = qt.Signal(object)
    idle = qt.Signal()
    directory_changed = qt.Signal(object)

    def __init__(self, model, tree, parent=None):
        super().__init__(parent)
        self.model = model
        self.tree = tree
        self.covers = CoverModel(model, self)
        self.tiles = qt.QListView()
        self.tiles.setModel(self.covers)
        self.tiles.setViewMode(qt.QListView.ViewMode.IconMode)
        self.tiles.setResizeMode(qt.QListView.ResizeMode.Adjust)
        self.tiles.setMovement(qt.QListView.Movement.Static)
        self.tiles.setIconSize(qt.QSize(120, 165))
        self.tiles.setGridSize(qt.QSize(170, 205))
        self.tiles.setWordWrap(True)
        self.columns = qt.QColumnView()
        self.columns.setModel(model)
        self.columns.setColumnWidths([240, 240, 240, 240])
        self.cover_queue = deque()
        self.cover_busy = False
        self.closing = False
        self.cover_path = None
        self.covers.cover_requested.connect(self._request_cover)
        for view in (tree, self.tiles, self.columns):
            self.addWidget(view)
            view.setSelectionMode(qt.QAbstractItemView.SelectionMode.ExtendedSelection)
            view.setEditTriggers(qt.QAbstractItemView.EditTrigger.NoEditTriggers)
            view.setContextMenuPolicy(qt.Qt.ContextMenuPolicy.CustomContextMenu)
            view.customContextMenuRequested.connect(lambda point, target=view: self._context(target, point))
            view.selectionModel().selectionChanged.connect(lambda *args, target=view: self._selection(target))
            view.doubleClicked.connect(lambda index: self.activated.emit(self.source_index(index)))
        self.root = None

    def source_index(self, index):
        return self.covers.mapToSource(index) if index.model() is self.covers else index

    def selected_rows(self):
        return list(dict.fromkeys(self.source_index(index) for index in
                                  self.currentWidget().selectionModel().selectedIndexes() if index.column() == 0))

    def current_index(self):
        return self.source_index(self.currentWidget().currentIndex())

    def browsing_directory(self):
        selected = self.selected_rows()
        index = self.current_index()
        if not any(index == item for item in selected):
            index = selected[-1] if selected else qt.QModelIndex()
        if index.isValid():
            path = Path(self.model.filePath(index))
            directory = path if self.currentIndex() == 2 and self.model.isDir(index) else path.parent
            if directory == self.root or self.root in directory.parents:
                return directory
        return self.root

    def _selection(self, view):
        if view is self.currentWidget():
            self.directory_changed.emit(self.browsing_directory())
            self.selection_changed.emit()

    def _context(self, view, point):
        if view is self.currentWidget():
            self.context_position = view.viewport().mapToGlobal(point)
            self.context_requested.emit(self.source_index(view.indexAt(point)))

    def set_root(self, path):
        self.root = Path(path)
        index = self.model.index(str(path))
        for view in (self.tree, self.tiles, self.columns):
            blocker = qt.QSignalBlocker(view.selectionModel())
            view.clearSelection()
            view.setCurrentIndex(qt.QModelIndex())
            view.setRootIndex(self.covers.mapFromSource(index) if view is self.tiles else index)
            blocker.unblock()
        self.tree.collapseAll()
        self.directory_changed.emit(self.root)
        self.selection_changed.emit()

    def set_mode(self, mode):
        selected = self.selected_rows()
        directory = self.browsing_directory()
        if directory != self.root:
            self.set_root(directory)
        self.setCurrentIndex(mode)
        selection = self.currentWidget().selectionModel()
        blocker = qt.QSignalBlocker(selection)
        selection.clearSelection()
        for source in selected:
            index = self.covers.mapFromSource(source) if mode == 1 else source
            selection.select(index, qt.QItemSelectionModel.SelectionFlag.Select | qt.QItemSelectionModel.SelectionFlag.Rows)
            selection.setCurrentIndex(index, qt.QItemSelectionModel.SelectionFlag.NoUpdate)
        blocker.unblock()
        self.directory_changed.emit(self.browsing_directory())
        self.selection_changed.emit()

    def _request_cover(self, path):
        if self.closing:
            return
        qt.QTimer.singleShot(0, lambda: self._enqueue_cover(path))

    def _visible_cover(self, path):
        index = self.covers.mapFromSource(self.model.index(path))
        return self.currentIndex() == 1 and self.tiles.visualRect(index).intersects(self.tiles.viewport().rect())

    def _enqueue_cover(self, path):
        if self.closing or not self._visible_cover(path):
            self.covers.requested.discard(path)
            return
        self.cover_queue.append(path)
        self._next_cover()

    def _next_cover(self):
        if self.cover_busy or self.closing or not self.cover_queue:
            return
        self.cover_path = self.cover_queue.popleft()
        path = self.cover_path
        if not self._visible_cover(path):
            self.covers.requested.discard(path)
            qt.QTimer.singleShot(0, self._next_cover)
            return
        self.cover_busy = True
        self.operation = Operation(lambda: ComicPages(path).cover((120, 165)), self)
        revision = self.covers.revisions.get(path, 0)
        self.operation.completed.connect(lambda data, error: self._cover_loaded(path, revision, data or b''))
        self.operation.finished.connect(self._cover_finished)
        self.operation.start()

    def _cover_loaded(self, path, revision, data):
        if revision == self.covers.revisions.get(path, 0):
            self.covers.complete(path, data)
        else:
            self.covers.requested.discard(path)
            self.tiles.viewport().update()

    def _cover_finished(self):
        self.cover_busy = False
        self.operation.deleteLater()
        if self.closing:
            self.idle.emit()
        else:
            self._next_cover()

    def stop(self):
        self.closing = True
        self.cover_queue.clear()
        return self.cover_busy
