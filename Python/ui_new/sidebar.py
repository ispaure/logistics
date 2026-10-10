"""Scrollable destinations and a grouped document-launcher overlay."""
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
            painter.drawRoundedRect(qt.QRectF(3, 3, 18, 18), 1.5, 1.5)
            painter.drawLine(qt.QLineF(3, 12, 21, 12))
            painter.drawLine(qt.QLineF(11, 12, 11, 21))
            bubble = qt.QPainterPath()
            bubble.moveTo(7, 6); bubble.lineTo(17, 6); bubble.lineTo(17, 9)
            bubble.lineTo(11, 9); bubble.lineTo(9, 11); bubble.lineTo(9, 9)
            bubble.lineTo(7, 9); bubble.closeSubpath()
            painter.drawPath(bubble)
        elif self.name == 'epub':
            book = qt.QPainterPath()
            book.moveTo(12, 6)
            book.cubicTo(9, 3, 5, 3, 2, 4); book.lineTo(2, 19)
            book.cubicTo(6, 18, 9, 19, 12, 21)
            book.cubicTo(15, 19, 18, 18, 22, 19); book.lineTo(22, 4)
            book.cubicTo(19, 3, 15, 3, 12, 6); book.closeSubpath()
            painter.drawPath(book)
            painter.drawLine(qt.QLineF(12, 6, 12, 21))
            for y in (9, 13):
                painter.drawLine(qt.QLineF(5, y, 9, y+1))
                painter.drawLine(qt.QLineF(15, y+1, 19, y))
        elif self.name in ('text', 'markdown'):
            painter.drawRoundedRect(qt.QRectF(2, 3, 20, 18), 2, 2)
            if self.name == 'text':
                for points in (((8, 8), (5, 12), (8, 16)), ((16, 8), (19, 12), (16, 16))):
                    painter.drawPolyline(qt.QPolygonF([qt.QPointF(x, y) for x, y in points]))
                painter.drawLine(qt.QLineF(14, 7, 10, 17))
            else:
                painter.drawPolyline(qt.QPolygonF([qt.QPointF(x, y) for x, y in
                    ((5, 16), (5, 8), (9, 13), (13, 8), (13, 16))]))
                painter.drawLine(qt.QLineF(17.5, 8, 17.5, 16))
                painter.drawPolyline(qt.QPolygonF([qt.QPointF(15.5, 14), qt.QPointF(17.5, 16), qt.QPointF(19.5, 14)]))
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


class DestinationGlyph(qt.QLabel):
    """A palette-aware, passive icon beside a document section's name."""

    def setIcon(self, icon):
        self.setPixmap(icon.pixmap(qt.QSize(24, 24)))


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
        self.setFixedWidth(60)
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
        panel = self.document_overlay = qt.QFrame(self, qt.Qt.WindowType.Popup)
        panel.setObjectName('documentOverlay')
        panel.setAccessibleName('Document launchers and open documents')
        panel.installEventFilter(self)
        panel.setStyleSheet("""
            QFrame#documentOverlay { border: 1px solid palette(mid); border-radius: 10px; background: palette(window); }
            QFrame#documentOverlay QTreeWidget { border: none; background: palette(window); }
            QFrame#documentOverlay QToolButton { border: 1px solid palette(mid); border-radius: 6px; padding: 4px; }
            QFrame#documentOverlay QToolButton:hover { background: palette(midlight); }
            QFrame#documentOverlay QToolButton:focus { border: 1px solid palette(highlight); }
            QFrame#documentOverlay QToolButton:pressed { background: palette(highlight); color: palette(highlighted-text); }
            QFrame#documentOverlay QLabel#documentHeading { font-weight: bold; font-size: 14px; }
        """)
        panel.resize(420, 420)
        panel_layout = qt.QVBoxLayout(panel)
        panel_layout.setContentsMargins(12, 12, 12, 12)
        panel_layout.setSpacing(10)
        heading = qt.QHBoxLayout()
        title = qt.QLabel('Documents'); title.setObjectName('documentHeading')
        heading.addWidget(title, 1)
        close = qt.QToolButton(); close.setText('×'); close.setAccessibleName('Close document overlay')
        close.clicked.connect(panel.hide); heading.addWidget(close)
        panel_layout.addLayout(heading)
        self.document_tree = qt.QTreeWidget(panel)
        self.document_tree.setHeaderHidden(True)
        self.document_tree.setAccessibleName('Documents grouped by editor')
        self.document_tree.setIndentation(32)
        self.document_tree.setRootIsDecorated(False)
        self.document_tree.setItemsExpandable(False)
        self.document_tree.setExpandsOnDoubleClick(False)
        self.document_tree.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document_tree.itemClicked.connect(self._select_tree_document)
        panel_layout.addWidget(self.document_tree)
        self.launchers = {}
        self.editor_buttons = {}
        self.editor_new_buttons = {}
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
        button.setCheckable(not key.startswith('editor:'))
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
            if tabs.tabText(index) == "Bulk Rename":
                self.pages["rename"] = page
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
        self.current_page = page
        is_tool = page is not None and page not in self.pages.values() and page is not self.documents
        for key, button in self.buttons.items():
            if key.startswith('editor:') or key == 'rename':
                button.setChecked(False)
                continue
            if key == 'tools':
                checked = is_tool
            elif key == 'documents':
                checked = page is self.documents or self.document_overlay.isVisible()
            else:
                checked = page is self.pages.get(key)
            button.setChecked(checked)
        for action in self.tools_menu.actions():
            action.setChecked(action.data() is page)

    def eventFilter(self, watched, event):
        if watched is self.document_overlay and event.type() in (qt.QEvent.Type.Show, qt.QEvent.Type.Hide):
            self.set_current(getattr(self, 'current_page', None))
        return super().eventFilter(watched, event)

    def _open_document(self, window, *, attach=False, tab=None):
        self.document_overlay.hide()
        if tab is not None:
            window.tabs.setCurrentWidget(tab)
        if attach:
            self.documents.attach(window)
        else:
            self.documents.present(window)

    def show_documents(self):
        if self.document_overlay.isVisible():
            self.document_overlay.hide()
            return
        self._populate_document_tree()
        button = self.buttons['documents']
        point = button.mapToGlobal(qt.QPoint(button.width() + 8, 0))
        screen = button.screen().availableGeometry()
        overlay = self.document_overlay
        overlay.resize(min(420, screen.width()), min(420, screen.height()))
        point.setX(max(screen.left(), min(point.x(), screen.right() - overlay.width() + 1)))
        point.setY(max(screen.top(), min(point.y(), screen.bottom() - overlay.height() + 1)))
        overlay.move(point)
        overlay.show()
        self.document_tree.setFocus()

    def _refresh_editors(self):
        from features import registry
        from features.contributions import DocumentLauncherContribution
        entries = [DocumentLauncherContribution('markdown', 'Markdown Editor', self._open_markdown, 'markdown', 20, self._new_markdown)]
        entries.extend(entry.contribution for entry in registry.get_document_launchers())
        self.launchers = {entry.editor_id: entry for entry in sorted(entries, key=lambda item: item.order)}
    def _launch_editor(self, key, *, new=False):
        self.document_overlay.hide()
        launcher = self.launchers[key]
        callback = launcher.new_document if new else launcher.open_document
        callback(self.documents)
        self._populate_document_tree()

    def _open_markdown(self, parent):
        from commonUtils.ui.markdown.window import open_markdown
        path, _ = qt.QFileDialog.getOpenFileName(parent, 'Open Markdown', '', 'Markdown (*.md *.markdown);;All files (*)')
        if path:
            return open_markdown(path, allow_edit=True)

    def _new_markdown(self, parent):
        from commonUtils.ui.markdown.window import open_markdown
        return open_markdown(None, allow_edit=True)

    def _open_bulk_rename(self):
        from ui_new.bulk_rename import open_bulk_rename
        return open_bulk_rename(parent=self.window())

    def _populate_document_tree(self):
        self.document_tree.clear()
        self.editor_groups = {}
        self.editor_buttons = {}
        self.editor_new_buttons = {}
        for key, launcher in self.launchers.items():
            group = qt.QTreeWidgetItem(self.document_tree)
            group.setData(0, qt.Qt.ItemDataRole.AccessibleTextRole, launcher.name)
            group.setData(0, qt.Qt.ItemDataRole.UserRole, ('editor', key))
            group.setFlags(group.flags() & ~qt.Qt.ItemFlag.ItemIsSelectable)
            row = qt.QWidget()
            row.setAutoFillBackground(True)
            row.setBackgroundRole(qt.QPalette.ColorRole.Window)
            layout = qt.QHBoxLayout(row)
            layout.setContentsMargins(4, 6, 4, 6)
            layout.setSpacing(8)
            glyph = DestinationGlyph(); glyph.setFixedSize(24, 24)
            set_painted_icon(glyph, DestinationIcon, launcher.icon or key)
            layout.addWidget(glyph)
            label = qt.QLabel(launcher.name)
            label.setToolTip(launcher.name)
            layout.addWidget(label, 1)
            if launcher.new_document:
                new_button = qt.QToolButton(); new_button.setText('New')
                new_button.setFixedWidth(48)
                new_button.setAccessibleName('New '+launcher.name)
                new_button.setToolTip('Create a new document in '+launcher.name)
                new_button.clicked.connect(lambda checked=False, editor=key: self._launch_editor(editor, new=True))
                layout.addWidget(new_button)
                self.editor_new_buttons[key] = new_button
            else:
                layout.addSpacing(48)
            button = qt.QToolButton(); button.setText('Open…'); button.setFixedWidth(64)
            button.setAccessibleName('Open '+launcher.name)
            button.setToolTip('Open a document in '+launcher.name)
            button.clicked.connect(lambda checked=False, editor=key: self._launch_editor(editor))
            layout.addWidget(button)
            self.editor_buttons[key] = button
            group.setSizeHint(0, row.sizeHint())
            self.document_tree.setItemWidget(group, 0, row)
            group.setExpanded(True)
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
