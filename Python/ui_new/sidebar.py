"""Scrollable destination icons and persistent, editor-grouped documents."""
from commonUtils.ui import pyside as qt
from commonUtils.ui.icons import set_painted_icon


class DestinationIcon(qt.QIconEngine):
    def __init__(self, name):
        super().__init__()
        self.name = name

    def clone(self):
        return DestinationIcon(self.name)

    def paint(self, painter, rect, mode, state):
        painter.save()
        painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
        painter.translate(rect.x(), rect.y())
        painter.scale(rect.width()/24, rect.height()/24)
        palette = qt.QApplication.palette()
        role = qt.QPalette.ColorRole.Highlight if state == qt.QIcon.State.On else qt.QPalette.ColorRole.ButtonText
        painter.setPen(qt.QPen(palette.color(role), 1.6))
        painter.setBrush(qt.Qt.BrushStyle.NoBrush)
        if self.name in ('browser', 'actions'):
            painter.drawRoundedRect(qt.QRectF(2, 6, 20, 15), 2, 2)
            painter.drawPolyline(qt.QPolygonF([qt.QPointF(2, 9), qt.QPointF(2, 3), qt.QPointF(9, 3), qt.QPointF(12, 6)]))
            if self.name == 'actions':
                painter.drawArc(qt.QRectF(8, 10, 10, 8), 30 * 16, 280 * 16)
                painter.drawPolyline(qt.QPolygonF([qt.QPointF(16, 9), qt.QPointF(19, 11), qt.QPointF(16, 13)]))
        elif self.name == 'rename':
            font = painter.font(); font.setPointSizeF(8); font.setBold(True); painter.setFont(font)
            painter.drawText(qt.QRectF(1, 3, 22, 18), qt.Qt.AlignmentFlag.AlignCenter, 'A→B')
        elif self.name == 'hub':
            for y in (3, 10, 17):
                painter.drawRoundedRect(qt.QRectF(3, y, 18, 4), 1, 1)
                painter.drawPoint(qt.QPointF(17, y+2))
        elif self.name == 'comic':
            for x in (3, 13):
                for y in (3, 13):
                    painter.drawRect(qt.QRectF(x, y, 8, 8))
        elif self.name == 'epub':
            painter.drawRoundedRect(qt.QRectF(3, 4, 18, 16), 2, 2)
            painter.drawLine(qt.QLineF(12, 4, 12, 20))
            for y in (8, 12, 16):
                painter.drawLine(qt.QLineF(5, y, 10, y))
                painter.drawLine(qt.QLineF(14, y, 19, y))
        elif self.name in ('text', 'markdown'):
            painter.drawRoundedRect(qt.QRectF(3, 3, 18, 18), 2, 2)
            painter.drawText(qt.QRectF(3, 3, 18, 18), qt.Qt.AlignmentFlag.AlignCenter, '</>' if self.name == 'text' else 'M↓')
        elif self.name == 'documents':
            painter.drawRoundedRect(qt.QRectF(6, 3, 15, 18), 1, 1)
            painter.drawPolyline(qt.QPolygonF([qt.QPointF(3, 6), qt.QPointF(3, 21), qt.QPointF(17, 21)]))
            for y in (8, 12, 16):
                painter.drawLine(qt.QLineF(10, y, 17, y))
        elif self.name == 'controller':
            path = qt.QPainterPath()
            path.moveTo(7, 7); path.lineTo(17, 7)
            path.cubicTo(21, 7, 24, 20, 20, 20)
            path.cubicTo(18, 20, 17, 16, 15, 16)
            path.lineTo(9, 16)
            path.cubicTo(7, 16, 6, 20, 4, 20)
            path.cubicTo(0, 20, 3, 7, 7, 7)
            painter.drawPath(path)
            painter.drawLine(qt.QLineF(5, 11, 11, 11))
            painter.drawLine(qt.QLineF(8, 8, 8, 14))
            painter.drawEllipse(qt.QPointF(17, 10), .8, .8)
            painter.drawEllipse(qt.QPointF(19, 13), .8, .8)
        elif self.name == 'archives':
            painter.drawRoundedRect(qt.QRectF(4, 3, 16, 18), 2, 2)
            painter.drawLine(qt.QLineF(4, 8, 20, 8))
            for y in (4, 10, 13, 16):
                painter.drawLine(qt.QLineF(11, y, 13, y))
            painter.drawRoundedRect(qt.QRectF(10, 18, 4, 3), .5, .5)
        elif self.name == 'git':
            painter.drawLine(qt.QLineF(7, 6, 7, 18))
            path = qt.QPainterPath(qt.QPointF(7, 15))
            path.cubicTo(7, 10, 17, 15, 17, 7)
            painter.drawPath(path)
            for x, y in ((7, 4), (7, 20), (17, 5)):
                painter.setBrush(palette.color(qt.QPalette.ColorRole.Window))
                painter.drawEllipse(qt.QPointF(x, y), 2.5, 2.5)
        elif self.name == 'tools':
            for x in (4, 14):
                for y in (4, 14):
                    painter.drawRoundedRect(qt.QRectF(x, y, 6, 6), 1, 1)
        else:
            for y, x in ((5, 8), (12, 16), (19, 10)):
                painter.drawLine(qt.QLineF(3, y, 21, y))
                painter.drawEllipse(qt.QPointF(x, y), 2, 2)
        painter.restore()

    def pixmap(self, size, mode, state):
        pixmap = qt.QPixmap(size)
        pixmap.fill(qt.Qt.GlobalColor.transparent)
        painter = qt.QPainter(pixmap)
        self.paint(painter, pixmap.rect(), mode, state)
        painter.end()
        return pixmap


class ActivityButton(qt.QToolButton):
    unread = 0

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.unread:
            painter = qt.QPainter(self)
            painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
            painter.setPen(qt.Qt.PenStyle.NoPen)
            painter.setBrush(qt.QColor('#c84c4c'))
            badge = qt.QRectF(self.width() - 18, 1, 16, 16)
            painter.drawEllipse(badge)
            painter.setPen(qt.QColor('white'))
            font = painter.font(); font.setPointSizeF(8); font.setBold(True); painter.setFont(font)
            painter.drawText(badge, qt.Qt.AlignmentFlag.AlignCenter, str(min(9, self.unread)))


class DestinationRail(qt.QWidget):
    selected = qt.Signal(object)

    def __init__(self, documents, parent=None):
        super().__init__(parent)
        self.documents = documents
        self.actions = None
        self.buttons = {}
        self.pages = {}
        self.setFixedWidth(320)
        self.setAccessibleName('Main destinations')
        outer = qt.QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        icon_scroll = qt.QScrollArea(self)
        icon_scroll.setWidgetResizable(True)
        icon_scroll.setFixedWidth(60)
        icon_scroll.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        icon_scroll.setFrameShape(qt.QFrame.Shape.NoFrame)
        icons = qt.QWidget()
        icon_scroll.setWidget(icons)
        outer.addWidget(icon_scroll)
        panel = qt.QWidget(self)
        panel_layout = qt.QVBoxLayout(panel)
        panel_layout.setContentsMargins(4, 10, 4, 4)
        panel_layout.addWidget(qt.QLabel('Documents'))
        self.document_tree = qt.QTreeWidget(panel)
        self.document_tree.setHeaderHidden(True)
        self.document_tree.setAccessibleName('Documents grouped by editor')
        self.document_tree.setIndentation(16)
        self.document_tree.itemClicked.connect(self._select_tree_document)
        panel_layout.addWidget(self.document_tree)
        outer.addWidget(panel, 1)
        self.launchers = {}
        self.editor_buttons = {}
        self.editor_groups = {}
        layout = qt.QVBoxLayout(icons)
        layout.setContentsMargins(6, 10, 6, 10)
        layout.setSpacing(8)
        for key, title in [('browser', 'File Browser'), ('hub', 'Folder Hub'),
                           ('documents', 'Open documents'), ('actions', 'Folder Actions'), ('tools', 'Tools')]:
            button = self._button(key, title)
            layout.addWidget(button)
            if key == 'actions':
                self.workspace_destinations = qt.QVBoxLayout()
                self.workspace_destinations.setContentsMargins(0, 0, 0, 0)
                self.workspace_destinations.setSpacing(8)
                layout.addLayout(self.workspace_destinations)
        self.feature_destinations = qt.QVBoxLayout()
        self.feature_destinations.setContentsMargins(0, 0, 0, 0)
        self.feature_destinations.setSpacing(8)
        layout.addLayout(self.feature_destinations)
        self.feature_buttons = set()
        self.workspace_buttons = set()
        layout.addStretch()
        layout.addWidget(self._button('settings', 'Settings'))
        self.tools_menu = qt.QMenu(self)
        self.buttons['tools'].setMenu(self.tools_menu)
        self.buttons['tools'].setPopupMode(qt.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.buttons['documents'].clicked.connect(self.show_documents)
        self.buttons['documents'].show()
        self.bulk_rename_button = self._button('rename', 'Bulk Rename')
        layout.insertWidget(layout.count()-2, self.bulk_rename_button)
        self.bulk_rename_button.clicked.connect(self._open_bulk_rename)
        self.buttons['actions'].hide()

    def _button(self, key, title, icon=None):
        button = ActivityButton(self) if key == 'actions' else qt.QToolButton(self)
        set_painted_icon(button, DestinationIcon, icon or key)
        button.setIconSize(qt.QSize(26, 26))
        button.setFixedSize(46, 42)
        button.setCheckable(key != 'rename' and not key.startswith('editor:'))
        button.setAccessibleName(title)
        button.setToolTip(title)
        button.setText(title)
        button.setToolButtonStyle(qt.Qt.ToolButtonStyle.ToolButtonIconOnly)
        if key not in ('tools', 'documents', 'rename') and not key.startswith('editor:'):
            button.clicked.connect(lambda checked=False, name=key: self.selected.emit(self.pages.get(name)))
        self.buttons[key] = button
        return button

    def refresh(self, tabs, core):
        core = {page: (order, name) for order, name, page in core}
        self.pages = {}
        for key in self.feature_buttons:
            self.buttons[key].hide()
        self.tools_menu.clear()
        workspace_entries = []
        for index in range(tabs.count()):
            page = tabs.widget(index)
            if page is self.documents:
                continue
            if page is self.actions:
                continue
            info = core.get(page)
            key = ('browser' if info and info[0] == 0 else
                   'hub' if info and info[0] == 5 else
                   'settings' if info and info[1] == 'Settings' else None)
            icon = page.property('navigation_icon')
            if key is None and icon:
                key = f'feature:{id(page)}'
                if key not in self.buttons:
                    button = self._button(key, tabs.tabText(index), icon)
                    if page.property('navigation_position') == 'workspace':
                        self.workspace_destinations.addWidget(button)
                        self.workspace_buttons.add(key)
                    else:
                        self.feature_destinations.addWidget(button)
                    self.feature_buttons.add(key)
                self.buttons[key].show()
                if key in self.workspace_buttons:
                    workspace_entries.append((page.property('navigation_order') or 100, tabs.tabText(index), self.buttons[key]))
            if key:
                self.pages[key] = page
            else:
                action = self.tools_menu.addAction(tabs.tabText(index))
                action.setData(page)
                action.setCheckable(True)
                action.setChecked(page is tabs.currentWidget())
                action.triggered.connect(lambda checked=False, target=page: self.selected.emit(target))
        for position, (_, _, button) in enumerate(sorted(workspace_entries, key=lambda entry: (entry[0], entry[1].casefold()))):
            self.workspace_destinations.insertWidget(position, button)
        for key in ('browser', 'hub', 'settings'):
            self.buttons[key].setVisible(key in self.pages)
        self.buttons['tools'].setVisible(bool(self.tools_menu.actions()))
        self.buttons['documents'].setVisible(True)
        self._refresh_editors()
        if self.actions is not None:
            self.pages['actions'] = self.actions
            button = self.buttons['actions']
            button.setVisible(bool(self.actions.count))
            button.unread = self.actions.unread_count
            button.setToolTip(f'Folder Actions ({self.actions.count}; {button.unread} unseen results)')
            button.setAccessibleName(button.toolTip())
            button.update()
        detached = sum(record['detached'] and not record['closed'] for record in self.documents.records.values())
        self.buttons['documents'].setToolTip(f'Open documents ({self.documents.count}; {detached} detached)')
        self.set_current(tabs.currentWidget())
        self._populate_document_tree()

    def set_current(self, page):
        is_tool = page is not None and page not in self.pages.values() and page is not self.documents
        for key, button in self.buttons.items():
            if key.startswith('editor:') or key == 'rename':
                button.setChecked(False)
                continue
            button.setChecked(is_tool if key == 'tools' else
                              page is (self.documents if key == 'documents' else self.pages.get(key)))
        for action in self.tools_menu.actions():
            action.setChecked(action.data() is page)

    def _open_document(self, window, *, attach=False, tab=None):
        if tab is not None:
            window.tabs.setCurrentWidget(tab)
        if attach:
            self.documents.attach(window)
        else:
            self.documents.present(window)

    def show_documents(self):
        activate = getattr(self.documents, 'activate', None)
        if activate is not None:
            activate()
        self._populate_document_tree()
        self.document_tree.setFocus()

    def _refresh_editors(self):
        from features import registry
        from features.contributions import DocumentLauncherContribution
        entries = [DocumentLauncherContribution('markdown', 'Markdown / Obsidian', self._open_markdown, 'markdown', 20)]
        entries.extend(entry.contribution for entry in registry.get_document_launchers())
        self.launchers = {entry.editor_id: entry for entry in sorted(entries, key=lambda item: item.order)}
        for key, button in self.editor_buttons.items():
            button.setVisible(key in self.launchers)
        for key, entry in self.launchers.items():
            if key not in self.editor_buttons:
                button = self._button('editor:'+key, entry.name, entry.icon)
                button.clicked.connect(lambda checked=False, editor=key: self._launch_editor(editor))
                self.workspace_destinations.addWidget(button)
                self.editor_buttons[key] = button
            self.editor_buttons[key].show()

    def _launch_editor(self, key):
        self.launchers[key].open_document(self.documents)
        self._populate_document_tree()

    def _open_markdown(self, parent):
        from commonUtils.ui.markdown.window import open_markdown
        path, _ = qt.QFileDialog.getOpenFileName(parent, 'Open Markdown', '', 'Markdown (*.md *.markdown);;All files (*)')
        if path:
            return open_markdown(path, allow_edit=True)

    def _open_bulk_rename(self):
        from ui_new.bulk_rename import open_bulk_rename
        return open_bulk_rename(parent=self.window())

    def _populate_document_tree(self):
        expanded = {key: item.isExpanded() for key, item in self.editor_groups.items()}
        self.document_tree.clear()
        self.editor_groups = {}
        for key, launcher in self.launchers.items():
            group = qt.QTreeWidgetItem(self.document_tree, [launcher.name])
            group.setData(0, qt.Qt.ItemDataRole.UserRole, ('editor', key))
            row = qt.QWidget()
            row.setAutoFillBackground(True)
            layout = qt.QHBoxLayout(row); layout.setContentsMargins(0, 0, 0, 0)
            label = qt.QLabel(launcher.name)
            layout.addWidget(label, 1)
            button = qt.QToolButton(); button.setText('+'); button.setToolTip('Open '+launcher.name)
            button.setAccessibleName('Open '+launcher.name)
            button.clicked.connect(lambda checked=False, editor=key: self._launch_editor(editor))
            layout.addWidget(button)
            group.setSizeHint(0, qt.QSize(0, 30))
            self.document_tree.setItemWidget(group, 0, row)
            group.setExpanded(expanded.get(key, True))
            self.editor_groups[key] = group
        for window, label, tab, detached in getattr(self.documents, 'document_entries', lambda: [])():
            key = getattr(window, 'document_editor_id', 'other')
            if key not in self.editor_groups:
                self.editor_groups[key] = qt.QTreeWidgetItem(self.document_tree, [getattr(window, 'document_editor_name', 'Other documents')])
                self.editor_groups[key].setExpanded(True)
            item = qt.QTreeWidgetItem(self.editor_groups[key], [label + (' ↗' if detached else '')])
            item.setData(0, qt.Qt.ItemDataRole.UserRole, ('document', window, tab))
            item.setToolTip(0, label + (' — detached; click to reveal window' if detached else ''))
            if detached:
                back = qt.QToolButton(); back.setText('Bring back')
                back.clicked.connect(lambda checked=False, view=window, buffer=tab: self._open_document(view, tab=buffer, attach=True))
                row = qt.QWidget(); row.setAutoFillBackground(True); layout = qt.QHBoxLayout(row); layout.setContentsMargins(0, 0, 0, 0)
                title = qt.QPushButton(label); title.setFlat(True)
                title.clicked.connect(lambda checked=False, view=window, buffer=tab: self._open_document(view, tab=buffer))
                layout.addWidget(title, 1); layout.addWidget(back)
                self.document_tree.setItemWidget(item, 0, row)

    def _select_tree_document(self, item, column):
        data = item.data(0, qt.Qt.ItemDataRole.UserRole)
        if not data:
            return
        if data[0] == 'document':
            self._open_document(data[1], tab=data[2])
