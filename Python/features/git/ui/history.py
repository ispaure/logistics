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


class DescriptionDelegate(qt.QStyledItemDelegate):
    """Draw compact ref badges before the commit subject without HTML."""
    def paint(self, painter, option, index):
        commit = index.data(qt.Qt.ItemDataRole.UserRole)
        if commit is None: return super().paint(painter,option,index)
        background = qt.QStyleOptionViewItem(option)
        self.initStyleOption(background,index)
        background.text = ''
        option.widget.style().drawControl(qt.QStyle.ControlElement.CE_ItemViewItem,background,painter,option.widget)
        painter.save(); painter.setClipRect(option.rect); painter.setFont(option.font)
        x=option.rect.left()+4
        metrics=option.fontMetrics
        for ref in commit.decorations.split(', '):
            if not ref: continue
            label=ref.removeprefix('HEAD -> ')
            width=min(metrics.horizontalAdvance(label)+14,150)
            rect=qt.QRect(x,option.rect.top()+1,width,option.rect.height()-2)
            painter.setPen(qt.Qt.PenStyle.NoPen)
            painter.setBrush(qt.QColor('#cb671e' if '/' in label else '#216ab4'))
            painter.drawRoundedRect(rect,3,3)
            painter.setPen(qt.QColor('white'))
            painter.drawText(rect.adjusted(5,0,-5,0),qt.Qt.AlignmentFlag.AlignVCenter,
                metrics.elidedText(label,qt.Qt.TextElideMode.ElideRight,width-10))
            x+=width+4
        painter.setPen(option.palette.text().color())
        painter.drawText(qt.QRect(x,option.rect.top(),max(0,option.rect.right()-x),option.rect.height()),
            qt.Qt.AlignmentFlag.AlignVCenter,metrics.elidedText(commit.subject,qt.Qt.TextElideMode.ElideRight,max(0,option.rect.right()-x)))
        painter.restore()


class HistoryPanel(qt.QWidget):
    commit_selected = qt.Signal(object)
    blob_selected = qt.Signal(object)
    load_more = qt.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.search = qt.QLineEdit()
        self.search.setPlaceholderText('Filter loaded commits by message, author, hash, or ref')
        self.search.setAccessibleName('Search loaded history')
        self.search.textChanged.connect(self._filter)
        filters = qt.QHBoxLayout()
        filters.setContentsMargins(4,2,4,2)
        filters.setSpacing(4)
        self.branch_filter = qt.QComboBox()
        self.branch_filter.addItems(['All branches','Current branch'])
        self.branch_filter.currentIndexChanged.connect(self._filter)
        filters.addWidget(self.branch_filter)
        filters.addWidget(self.search,1)
        layout.addLayout(filters)
        self.head_oid = ''
        self.commits = []
        self.table = qt.QTreeWidget()
        self.table.setHeaderLabels(['Graph', 'Description', 'Commit', 'Author', 'Date'])
        self.table.setRootIsDecorated(False)
        self.table.setUniformRowHeights(True)
        self.table.setAccessibleName('Commit history')
        self.table.setItemDelegateForColumn(0, GraphDelegate(self.table))
        self.table.setItemDelegateForColumn(1, DescriptionDelegate(self.table))
        self.table.header().setSectionResizeMode(1, qt.QHeaderView.ResizeMode.Stretch)
        self.table.header().setStretchLastSection(False)
        self.table.setColumnWidth(0, 95)
        self.table.setColumnWidth(2, 80)
        self.table.setColumnWidth(3, 180)
        self.table.setColumnWidth(4, 155)
        self.table.currentItemChanged.connect(self._selected)
        layout.addWidget(self.table, 3)
        self.more = qt.QPushButton('Load 200 more commits')
        self.more.clicked.connect(self.load_more.emit)
        layout.addWidget(self.more)
        self.details = qt.QSplitter(qt.Qt.Orientation.Vertical)
        file_host = qt.QWidget()
        files_layout = qt.QVBoxLayout(file_host)
        files_layout.setContentsMargins(0,0,0,0)
        files_layout.setSpacing(2)
        self.file_mode = qt.QComboBox()
        self.file_mode.addItems(['Changed files (first parent)','Full tree at commit'])
        self.file_mode.currentIndexChanged.connect(lambda: self.commit_selected.emit(self.selected_commit()) if self.selected_commit() else None)
        files_layout.addWidget(self.file_mode)
        self.tree = qt.QTreeWidget()
        self.tree.setHeaderLabels(['Files', 'Status / type'])
        self.tree.setAccessibleName('Historical file tree')
        self.tree.header().setSectionResizeMode(0, qt.QHeaderView.ResizeMode.Stretch)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(1, qt.QHeaderView.ResizeMode.ResizeToContents)
        self.tree.currentItemChanged.connect(self._blob)
        files_layout.addWidget(self.tree,1)
        self.details.addWidget(file_host)
        self.metadata = qt.QPlainTextEdit()
        self.metadata.setReadOnly(True)
        self.metadata.setAccessibleName('Selected commit metadata')
        self.metadata.setLineWrapMode(qt.QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.details.addWidget(self.metadata)
        self.details.setSizes([180,170])

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
                item = qt.QTreeWidgetItem(['', subject, commit.oid[:8], commit.author, commit.date.replace('T',' ')[:19]])
                item.setData(0, qt.Qt.ItemDataRole.UserRole, row)
                item.setData(1, qt.Qt.ItemDataRole.UserRole, commit)
                item.setToolTip(1, subject)
                item.setToolTip(2, commit.oid)
                self.table.addTopLevelItem(item)
                if commit.oid == oid: self.table.setCurrentItem(item)
        self.more.setVisible(more)
        self._filter()

    def select_ref(self, oid):
        for i in range(self.table.topLevelItemCount()):
            item=self.table.topLevelItem(i)
            if item.data(1,qt.Qt.ItemDataRole.UserRole).oid == oid:
                self.table.setCurrentItem(item); self.table.scrollToItem(item)
                return

    def selected_commit(self):
        item = self.table.currentItem()
        return item.data(1, qt.Qt.ItemDataRole.UserRole) if item else None

    def _selected(self, item, previous):
        self.tree.clear()
        if item: self.commit_selected.emit(item.data(1, qt.Qt.ItemDataRole.UserRole))

    def _filter(self, *args):
        text = self.search.text().casefold()
        # Hiding intervening rows would make graph edges imply false ancestry.
        limited = bool(self.branch_filter.currentIndex())
        by_oid={c.oid:c for c in self.commits}
        reachable=set()
        pending=[self.head_oid] if limited else []
        while pending:
            oid=pending.pop()
            if oid in reachable: continue
            reachable.add(oid)
            if oid in by_oid: pending.extend(by_oid[oid].parents)
        self.table.setColumnHidden(0, bool(text) or limited)
        for i in range(self.table.topLevelItemCount()):
            item = self.table.topLevelItem(i)
            commit = item.data(1, qt.Qt.ItemDataRole.UserRole)
            item.setHidden((limited and commit.oid not in reachable) or text not in f'{commit.subject} {commit.author} {commit.oid} {commit.decorations}'.casefold())

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
                item = qt.QTreeWidgetItem([parts[-1], 'submodule' if entry.kind == 'commit' else entry.mode if entry.kind == 'change' else entry.kind])
                item.setData(0, qt.Qt.ItemDataRole.UserRole, entry)
                item.setToolTip(0, entry.path)
                if parent: parent.addChild(item)
                else: self.tree.addTopLevelItem(item)

    def select_first_file(self):
        def first(item):
            if item.data(0,qt.Qt.ItemDataRole.UserRole): return item
            for i in range(item.childCount()):
                found=first(item.child(i))
                if found: return found
        for i in range(self.tree.topLevelItemCount()):
            item=first(self.tree.topLevelItem(i))
            if item:
                self.tree.setCurrentItem(item)
                return

    def _blob(self, item, previous):
        if item:
            entry = item.data(0, qt.Qt.ItemDataRole.UserRole)
            if entry: self.blob_selected.emit(entry)
