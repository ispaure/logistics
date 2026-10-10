"""Commit graph, searchable history, and historical tree browsing widgets."""
from commonUtils.ui import pyside as qt
from ..graph import layout_graph


class GraphDelegate(qt.QStyledItemDelegate):
    COLORS = ('#579dd9', '#bf79ce', '#61b38d', '#d6a251', '#db7c80', '#6dafba')

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        row = index.data(qt.Qt.ItemDataRole.UserRole)
        if row is None: return
        painter.save()
        painter.setClipRect(option.rect)
        painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
        rect = option.rect
        center = rect.center().y()
        def x(lane): return rect.left() + 12 + lane * 14
        for source, target in row.incoming:
            painter.setPen(qt.QPen(qt.QColor(self.COLORS[source % len(self.COLORS)]), 2))
            painter.drawLine(qt.QPointF(x(source), rect.top()), qt.QPointF(x(target), center))
        for source, target in row.outgoing:
            painter.setPen(qt.QPen(qt.QColor(self.COLORS[target % len(self.COLORS)]), 2))
            painter.drawLine(qt.QPointF(x(source), center), qt.QPointF(x(target), rect.bottom() + 1))
        color = qt.QColor(self.COLORS[row.lane % len(self.COLORS)])
        painter.setPen(qt.QPen(color, 2))
        painter.setBrush(option.palette.base())
        painter.drawEllipse(qt.QPointF(x(row.lane), center), 4, 4)
        painter.restore()


class HistoryPanel(qt.QWidget):
    commit_selected = qt.Signal(object)
    blob_selected = qt.Signal(object)
    load_more = qt.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.search = qt.QLineEdit()
        self.search.setPlaceholderText('Filter loaded commits by message, author, hash, or ref')
        self.search.setAccessibleName('Search loaded history')
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)
        self.commits = []
        self.table = qt.QTreeWidget()
        self.table.setHeaderLabels(['Graph', 'Commit', 'Author', 'Date', 'Hash'])
        self.table.setRootIsDecorated(False)
        self.table.setUniformRowHeights(True)
        self.table.setAccessibleName('Commit history')
        self.table.setItemDelegateForColumn(0, GraphDelegate(self.table))
        self.table.header().setSectionResizeMode(1, qt.QHeaderView.ResizeMode.Stretch)
        self.table.header().setStretchLastSection(False)
        self.table.setColumnWidth(0, 95)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 85)
        self.table.setColumnWidth(4, 75)
        self.table.currentItemChanged.connect(self._selected)
        layout.addWidget(self.table, 3)
        self.more = qt.QPushButton('Load 200 more commits')
        self.more.clicked.connect(self.load_more.emit)
        layout.addWidget(self.more)
        self.tree = qt.QTreeWidget()
        self.tree.setHeaderLabels(['Files at selected commit', 'Type'])
        self.tree.setAccessibleName('Historical file tree')
        self.tree.header().setSectionResizeMode(0, qt.QHeaderView.ResizeMode.Stretch)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(1, qt.QHeaderView.ResizeMode.ResizeToContents)
        self.tree.currentItemChanged.connect(self._blob)
        layout.addWidget(self.tree, 2)

    def set_commits(self, commits, more=False):
        selected = self.selected_commit()
        oid = selected.oid if selected else ''
        self.commits = commits
        graph = layout_graph(commits)
        width = min(260, max((row.width for row in graph), default=1) * 14 + 22)
        self.table.setColumnWidth(0, max(80, width))
        with qt.QSignalBlocker(self.table):
            self.table.clear()
            for commit, row in zip(commits, graph):
                subject = commit.subject + (f'  · {commit.decorations}' if commit.decorations else '')
                item = qt.QTreeWidgetItem(['', subject, commit.author, commit.date[:10], commit.oid[:8]])
                item.setData(0, qt.Qt.ItemDataRole.UserRole, row)
                item.setData(1, qt.Qt.ItemDataRole.UserRole, commit)
                item.setToolTip(1, subject)
                item.setToolTip(4, commit.oid)
                self.table.addTopLevelItem(item)
                if commit.oid == oid: self.table.setCurrentItem(item)
        self.more.setVisible(more)
        self._filter()

    def selected_commit(self):
        item = self.table.currentItem()
        return item.data(1, qt.Qt.ItemDataRole.UserRole) if item else None

    def _selected(self, item, previous):
        self.tree.clear()
        if item: self.commit_selected.emit(item.data(1, qt.Qt.ItemDataRole.UserRole))

    def _filter(self):
        text = self.search.text().casefold()
        # Hiding intervening rows would make graph edges imply false ancestry.
        self.table.setColumnHidden(0, bool(text))
        for i in range(self.table.topLevelItemCount()):
            item = self.table.topLevelItem(i)
            commit = item.data(1, qt.Qt.ItemDataRole.UserRole)
            item.setHidden(text not in f'{commit.subject} {commit.author} {commit.oid} {commit.decorations}'.casefold())

    def set_tree(self, entries):
        with qt.QSignalBlocker(self.tree):
            self.tree.clear()
            folders = {}
            for entry in entries:
                parent = None
                parts = entry.path.split('/')
                for depth in range(1, len(parts)):
                    key = '/'.join(parts[:depth])
                    if key not in folders:
                        folder = qt.QTreeWidgetItem([parts[depth - 1], 'directory'])
                        if parent: parent.addChild(folder)
                        else: self.tree.addTopLevelItem(folder)
                        folders[key] = folder
                    parent = folders[key]
                item = qt.QTreeWidgetItem([parts[-1], 'submodule' if entry.kind == 'commit' else entry.kind])
                item.setData(0, qt.Qt.ItemDataRole.UserRole, entry)
                item.setToolTip(0, entry.path)
                if parent: parent.addChild(item)
                else: self.tree.addTopLevelItem(item)

    def _blob(self, item, previous):
        if item:
            entry = item.data(0, qt.Qt.ItemDataRole.UserRole)
            if entry: self.blob_selected.emit(entry)
