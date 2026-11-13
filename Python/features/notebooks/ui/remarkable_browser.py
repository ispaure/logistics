"""Read-only tablet navigation using the shared identity-based browser views."""
from collections import deque

from commonUtils.runtime.browsing import BrowseEntry, BrowseColumn, BrowseRole
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser.controls import navigation_button, ViewModeSelector
from commonUtils.ui.file_browser.entry_model import EntryModel
from commonUtils.ui.file_browser.keyboard import BrowserKeyboard
from commonUtils.ui.file_browser.navigation import BreadcrumbBar
from commonUtils.ui.file_browser.views import BrowserViews
from ..remarkable_store import ROOT


class TabletModel(EntryModel):
    def __init__(self, snapshot, parent=None):
        self.snapshot = snapshot
        self.visible = None
        super().__init__(self.entry(ROOT), (BrowseColumn('name', 'Name'), BrowseColumn('kind', 'Type')),
                         parent, max_entries=max(1, len(snapshot.entries)))
        # The snapshot is already normalized and complete, so there are no lazy
        # filesystem requests. Shared views consume its opaque IDs and ancestry.
        pending = deque([ROOT])
        while pending:
            parent_id = pending.popleft()
            children = snapshot.children[parent_id]
            for identity in children:
                self.tree.ensure(self.entry(identity), parent_id)
                if snapshot.entries[identity].directory:
                    pending.append(identity)
            self.tree.children[parent_id] = children

    def entry(self, identity):
        entry = self.snapshot.entries[identity]
        return BrowseEntry(identity, entry.title, entry.directory,
                           {'kind': 'Folder' if entry.directory else 'Document'}, payload=entry,
                           suffix='' if entry.directory else '.rmdoc')

    def _children(self, identity):
        children = super()._children(identity)
        return children if self.visible is None else tuple(key for key in children if key in self.visible)

    def filter(self, query, directory):
        self.beginResetModel()
        self.visible = self.snapshot.visible(query, directory)
        self.endResetModel()

    def data(self, index, role=qt.Qt.ItemDataRole.DisplayRole):
        identity = self.browse_identity(index)
        if identity is not None and role == qt.Qt.ItemDataRole.ToolTipRole:
            entry = self.snapshot.entries[identity]
            return '\n'.join(value for value in (entry.title, identity, entry.issue) if value)
        return super().data(index, role)


class TabletBreadcrumbs(BreadcrumbBar):
    def __init__(self, snapshot, parent=None):
        self.snapshot = snapshot
        super().__init__(parent)

    def _configure(self, button, identity):
        entry = self.snapshot.entries[identity]
        button.setText(entry.title)
        button.setToolTip(entry.title)
        button.setAccessibleName('Go to folder ' + entry.title)
        button.setIcon(self.style().standardIcon(qt.QStyle.StandardPixmap.SP_DirIcon))


class TabletBrowser(qt.QWidget):
    selection_changed = qt.Signal()
    retrieve = qt.Signal()
    refresh_requested = qt.Signal()

    def __init__(self, snapshot, parent=None):
        super().__init__(parent)
        self.snapshot = snapshot
        self.closing = False
        self.directory = ROOT
        self.history = [ROOT]
        self.history_index = 0
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        controls = qt.QHBoxLayout()
        self.back = navigation_button(self, 'Back', qt.QStyle.StandardPixmap.SP_ArrowBack)
        self.forward = navigation_button(self, 'Forward', qt.QStyle.StandardPixmap.SP_ArrowForward)
        self.up = navigation_button(self, 'Up one folder', qt.QStyle.StandardPixmap.SP_ArrowUp)
        self.refresh_button = navigation_button(self, 'Refresh tablet folders', qt.QStyle.StandardPixmap.SP_BrowserReload)
        self.breadcrumbs = TabletBreadcrumbs(snapshot, self)
        self.view_selector = ViewModeSelector(self, modes=(0, 1))
        for button in (self.back, self.forward, self.up, self.refresh_button):
            controls.addWidget(button)
        controls.addWidget(self.breadcrumbs, 1)
        controls.addWidget(self.view_selector)
        layout.addLayout(controls)
        self.search = qt.QLineEdit()
        self.search.setPlaceholderText('Filter this folder and its subfolders')
        self.search.setAccessibleName('Filter tablet notebooks and folders')
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        self.model = TabletModel(snapshot, self)
        self.tree = qt.QTreeView()
        self.tree.setModel(self.model)
        self.tree.setAccessibleName('Tablet notebooks and folders')
        self.tree.setUniformRowHeights(True)
        self.tree.header().setSectionResizeMode(0, qt.QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, qt.QHeaderView.ResizeMode.ResizeToContents)
        self.views = BrowserViews(self.model, self.tree, self, column_navigation=False)
        self.views.navigation_root = ROOT
        layout.addWidget(self.views, 1)
        self.view_selector.currentIndexChanged.connect(self.views.set_mode)
        self.views.selection_changed.connect(self.selection_changed)
        self.views.activated.connect(self.activate)
        self.breadcrumbs.requested.connect(self.navigate)
        self.up.clicked.connect(lambda: self.navigate(snapshot.entries[self.directory].parent))
        self.back.clicked.connect(lambda: self.step(-1))
        self.forward.clicked.connect(lambda: self.step(1))
        self.refresh_button.clicked.connect(self.refresh_requested)
        self.search.textChanged.connect(self.filter)
        self.keyboard = BrowserKeyboard(self, execute=self.command)
        self.navigate(ROOT, remember=False)

    def selected(self):
        rows = self.views.selected_rows()
        return self.model.browse_identity(rows[0]) if len(rows) == 1 else None

    def navigate(self, identity, *, remember=True):
        if self.closing or identity not in self.snapshot.children:
            return
        self.directory = identity
        self.search.clear()
        self.model.filter('', identity)
        self.views.set_root(identity)
        if remember and self.history[self.history_index] != identity:
            del self.history[self.history_index + 1:]
            self.history.append(identity)
            self.history = self.history[-100:]
            self.history_index = len(self.history) - 1
        self.breadcrumbs.set_paths(self.snapshot.ancestry(identity))
        self.back.setEnabled(self.history_index > 0)
        self.forward.setEnabled(self.history_index < len(self.history) - 1)
        self.up.setEnabled(identity != ROOT)

    def step(self, offset):
        index = self.history_index + offset
        if 0 <= index < len(self.history):
            self.history_index = index
            self.navigate(self.history[index], remember=False)

    def filter(self, query):
        selected = self.selected()
        self.model.filter(query, self.directory)
        self.views.set_root(self.directory)
        if query:
            self.tree.expandAll()
        if selected is not None:
            index = self.model.browse_index(selected)
            if index.isValid():
                self.views.select_source(index)
        self.selection_changed.emit()

    def activate(self, index):
        identity = self.model.browse_identity(index)
        if identity is None or self.closing:
            return
        if index.data(BrowseRole.Container):
            self.navigate(identity)
        else:
            self.views.select_source(index)
            self.retrieve.emit()

    def command(self, action):
        if action in ('back', 'forward', 'up'):
            getattr(self, action).click()
        elif action == 'open':
            rows = self.views.selected_rows()
            if len(rows) == 1:
                self.activate(rows[0])

    def stop(self):
        self.closing = True
        return self.views.stop()
