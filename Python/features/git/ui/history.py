"""Commit graph, searchable history, and historical tree browsing widgets."""
from commonUtils.ui import pyside as qt
from datetime import datetime
from html import escape
import re
from ..graph import layout_graph
from ..models import Commit
from .chrome import GRAPH_COLORS, status_icon, _draw_action

WORKING_COPY_ROLE = qt.Qt.ItemDataRole.UserRole + 1


def ref_badge(ref):
    ref = ref.removeprefix('HEAD -> ')
    return ('tag', ref.removeprefix('tag: ')) if ref.startswith('tag: ') else ('branch', ref)


class GraphDelegate(qt.QStyledItemDelegate):
    COLORS = GRAPH_COLORS
    LIGHT_COLORS = ('#0072B2', '#D55E00', '#927000', '#00845F', '#A45686', '#A96C00', '#34538D')

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        row = index.data(qt.Qt.ItemDataRole.UserRole)
        if row is None: return
        working_copy = index.siblingAtColumn(1).data(WORKING_COPY_ROLE)
        colors = self.COLORS if option.palette.base().color().lightness() < 128 else self.LIGHT_COLORS
        painter.save()
        painter.setClipRect(option.rect)
        painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
        rect = option.rect
        center = rect.center().y()
        def x(lane): return rect.left() + 12 + lane * 14
        for source, target in row.incoming:
            painter.setPen(qt.QPen(qt.QColor(colors[source % len(colors)]), 2))
            painter.drawLine(qt.QPointF(x(source), rect.top()), qt.QPointF(x(target), center))
        for source, target in row.outgoing:
            painter.setPen(qt.QPen(qt.QColor('#a0a5ad' if working_copy else colors[target % len(colors)]), 2))
            painter.drawLine(qt.QPointF(x(source), center), qt.QPointF(x(target), rect.bottom() + 1))
        color = qt.QColor('#a0a5ad' if working_copy else colors[row.lane % len(colors)])
        painter.setPen(qt.QPen(color, 2))
        painter.setBrush(option.palette.base() if working_copy else qt.QBrush(color))
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
        painter.save(); painter.setClipRect(option.rect); painter.setFont(background.font)
        x=option.rect.left()+4
        metrics=background.fontMetrics
        for ref in commit.decorations.split(', '):
            if not ref: continue
            kind, label = ref_badge(ref)
            width=min(metrics.horizontalAdvance(label)+30,166)
            rect=qt.QRect(x,option.rect.top()+1,width,option.rect.height()-2)
            painter.setPen(qt.Qt.PenStyle.NoPen)
            painter.setBrush(qt.QColor('#cb671e' if '/' in label else '#216ab4'))
            painter.drawRoundedRect(rect,3,3)
            painter.save(); painter.translate(x + 5, option.rect.center().y() - 7); painter.scale(.5, .5)
            _draw_action(painter, kind, 'white'); painter.restore()
            painter.setPen(qt.QColor('white'))
            painter.drawText(rect.adjusted(23,0,-5,0),qt.Qt.AlignmentFlag.AlignVCenter,
                metrics.elidedText(label,qt.Qt.TextElideMode.ElideRight,width-28))
            x+=width+4
        selected = bool(option.state & qt.QStyle.StateFlag.State_Selected)
        painter.setPen(background.palette.color(qt.QPalette.ColorRole.HighlightedText if selected else qt.QPalette.ColorRole.Text))
        painter.drawText(qt.QRect(x,option.rect.top(),max(0,option.rect.right()-x),option.rect.height()),
            qt.Qt.AlignmentFlag.AlignVCenter,metrics.elidedText(commit.subject,qt.Qt.TextElideMode.ElideRight,max(0,option.rect.right()-x)))
        painter.restore()


class HistoryPanel(qt.QWidget):
    commit_selected = qt.Signal(object)
    blob_selected = qt.Signal(object)
    load_more = qt.Signal()
    parent_requested = qt.Signal(str)
    working_copy_selected = qt.Signal()

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
        self.uncommitted_count = 0
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
        file_filters = qt.QHBoxLayout()
        file_filters.setContentsMargins(2, 2, 2, 2)
        file_filters.setSpacing(4)
        file_filters.addWidget(self.file_mode)
        self.file_search = qt.QLineEdit()
        self.file_search.setPlaceholderText('Search files by name or path')
        self.file_search.setClearButtonEnabled(True)
        self.file_search.setAccessibleName('Search commit files')
        self.file_search.textChanged.connect(self._filter_files)
        file_filters.addWidget(self.file_search, 1)
        files_layout.addLayout(file_filters)
        self.tree = qt.QTreeWidget()
        self.tree.setColumnCount(1)
        self.tree.setHeaderHidden(True)
        self.tree.setAccessibleName('Historical file tree')
        self.tree.setUniformRowHeights(True)
        self.tree.header().setSectionResizeMode(0, qt.QHeaderView.ResizeMode.Stretch)
        self.tree.currentItemChanged.connect(self._blob)
        files_layout.addWidget(self.tree,1)
        self.details.addWidget(file_host)
        self.metadata = qt.QTextBrowser()
        self.metadata.setReadOnly(True)
        self.metadata.setAccessibleName('Selected commit metadata')
        self.metadata.setOpenLinks(False)
        self.metadata.setOpenExternalLinks(False)
        self.metadata.anchorClicked.connect(self._parent_link)
        self.details.addWidget(self.metadata)
        self.details.setSizes([180,170])

    def set_commits(self, commits, more=False):
        working_selected = self.working_copy_is_selected()
        selected = self.selected_commit()
        oid = selected.oid if selected else ''
        self.commits = commits
        graph_commits = commits
        if self.uncommitted_count:
            parents = (self.head_oid,) if re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', self.head_oid) else ()
            graph_commits = [Commit('working-copy', parents, '', '', 'Uncommitted changes'), *commits]
        graph = layout_graph(graph_commits)
        width = min(260, max((row.width for row in graph), default=1) * 14 + 22)
        self.table.setColumnWidth(0, max(80, width))
        with qt.QSignalBlocker(self.table):
            self.table.clear()
            for commit, row in zip(graph_commits, graph):
                if commit.oid == 'working-copy':
                    item = qt.QTreeWidgetItem(['', 'Uncommitted changes', '*', '*', 'Today'])
                    item.setData(0, qt.Qt.ItemDataRole.UserRole, row)
                    item.setData(1, WORKING_COPY_ROLE, True)
                    item.setToolTip(1, f'{self.uncommitted_count} changed files — review in History')
                    font = self.table.font(); font.setBold(True); item.setFont(1, font)
                    self.table.addTopLevelItem(item)
                    if working_selected: self.table.setCurrentItem(item)
                    continue
                subject = commit.subject + (f'  · {commit.decorations}' if commit.decorations else '')
                item = qt.QTreeWidgetItem(['', subject, commit.oid[:8], commit.author, commit.date.replace('T',' ')[:19]])
                item.setData(0, qt.Qt.ItemDataRole.UserRole, row)
                item.setData(1, qt.Qt.ItemDataRole.UserRole, commit)
                item.setToolTip(1, subject)
                item.setToolTip(2, commit.oid)
                if commit.oid == self.head_oid:
                    font = self.table.font(); font.setBold(True)
                    for column in range(self.table.columnCount()): item.setFont(column, font)
                self.table.addTopLevelItem(item)
                if commit.oid == oid: self.table.setCurrentItem(item)
        self.more.setVisible(more)
        self._filter()

    def select_ref(self, oid):
        for i in range(self.table.topLevelItemCount()):
            item=self.table.topLevelItem(i)
            commit = item.data(1,qt.Qt.ItemDataRole.UserRole)
            if commit and commit.oid == oid:
                self.table.setCurrentItem(item); self.table.scrollToItem(item)
                return True
        return False

    def _parent_link(self, url):
        oid = url.toString()
        if re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', oid):
            self.parent_requested.emit(oid)

    def set_metadata(self, details):
        subject, _, body = details['message'].strip().partition('\n')
        message = '<b>' + escape(subject) + '</b>'
        if body: message += '<br>' + escape(body).replace('\n', '<br>')
        parents = ', '.join(f'<a href="{oid}">{oid[:10]}</a>'
                            for oid in details['parents'].split()
                            if re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', oid))
        try:
            date = datetime.fromisoformat(details['date']).astimezone().strftime('%B %d, %Y at %H:%M:%S %Z')
        except ValueError:
            date = details['date']
        muted = self.palette().color(qt.QPalette.ColorRole.PlaceholderText).name()
        fields = [('Commit', escape(details['oid'])), ('Parents', parents or 'None (root commit)'),
                  ('Author', escape(f"{details['author']} <{details['email']}>")),
                  ('Date', escape(date)), ('Labels', escape(details['labels'].strip()) or '—')]
        rows = ''.join(f'<tr><td style="color:{muted}; padding-right:8px">{label}:</td><td>{value}</td></tr>'
                       for label, value in fields)
        self.metadata.setHtml(f'<p>{message}</p><table cellspacing="2">{rows}</table>')

    def working_copy_is_selected(self):
        item = self.table.currentItem()
        return bool(item and item.data(1, WORKING_COPY_ROLE))

    def selected_commit(self):
        item = self.table.currentItem()
        return item.data(1, qt.Qt.ItemDataRole.UserRole) if item else None

    def _selected(self, item, previous):
        if item and item.data(1, WORKING_COPY_ROLE):
            self.working_copy_selected.emit()
            return
        # Removing the selected file can briefly select another old item. That
        # must not launch a file read ahead of the new commit's metadata read.
        with qt.QSignalBlocker(self.tree): self.tree.clear()
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
            if not commit:
                item.setHidden(text not in 'uncommitted changes')
                continue
            item.setHidden((limited and commit.oid not in reachable) or text not in f'{commit.subject} {commit.author} {commit.oid} {commit.decorations}'.casefold())

    def set_tree(self, entries):
        with qt.QSignalBlocker(self.tree):
            self.tree.clear()
            folders = {}
            hierarchical = bool(self.file_mode.currentIndex())
            self.tree.setRootIsDecorated(hierarchical)
            for entry in entries:
                parent = None
                parts = entry.path.split('/')
                for depth in range(1, len(parts)) if hierarchical else ():
                    key = '/'.join(parts[:depth])
                    if key not in folders:
                        folder = qt.QTreeWidgetItem([parts[depth - 1]])
                        if parent: parent.addChild(folder)
                        else: self.tree.addTopLevelItem(folder)
                        folders[key] = folder
                    parent = folders[key]
                item = qt.QTreeWidgetItem([parts[-1] if hierarchical else entry.path])
                item.setData(0, qt.Qt.ItemDataRole.UserRole, entry)
                if entry.kind == 'change': item.setIcon(0, status_icon(entry.mode))
                item.setToolTip(0, entry.path)
                if parent: parent.addChild(item)
                else: self.tree.addTopLevelItem(item)
        self._filter_files()

    def _filter_files(self):
        query = self.file_search.text().casefold()
        def visible(item):
            entry = item.data(0, qt.Qt.ItemDataRole.UserRole)
            children = [visible(item.child(i)) for i in range(item.childCount())]
            matches = query in entry.path.casefold() if entry else any(children)
            item.setHidden(not matches)
            if query and children: item.setExpanded(True)
            return matches
        with qt.QSignalBlocker(self.tree):
            for i in range(self.tree.topLevelItemCount()):
                visible(self.tree.topLevelItem(i))

    def select_first_file(self):
        def first(item):
            if item.isHidden(): return None
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
