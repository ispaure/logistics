"""Compact destination rail with on-demand tools and document lists."""
from commonUtils.ui import pyside as qt


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
        elif self.name == 'hub':
            for y in (3, 10, 17):
                painter.drawRoundedRect(qt.QRectF(3, y, 18, 4), 1, 1)
                painter.drawPoint(qt.QPointF(17, y+2))
        elif self.name == 'documents':
            painter.drawRoundedRect(qt.QRectF(6, 3, 15, 18), 1, 1)
            painter.drawPolyline(qt.QPolygonF([qt.QPointF(3, 6), qt.QPointF(3, 21), qt.QPointF(17, 21)]))
            for y in (8, 12, 16):
                painter.drawLine(qt.QLineF(10, y, 17, y))
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
        self.setFixedWidth(60)
        self.setAccessibleName('Main destinations')
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(6, 10, 6, 10)
        layout.setSpacing(8)
        for key, title in [('browser', 'File Browser'), ('hub', 'Folder Hub'),
                           ('documents', 'Open documents'), ('actions', 'Folder Actions'), ('tools', 'Tools')]:
            button = self._button(key, title)
            layout.addWidget(button)
        layout.addStretch()
        layout.addWidget(self._button('settings', 'Settings'))
        self.tools_menu = qt.QMenu(self)
        self.buttons['tools'].setMenu(self.tools_menu)
        self.buttons['tools'].setPopupMode(qt.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.buttons['documents'].clicked.connect(self.show_documents)
        self.document_popup = qt.QFrame(self, qt.Qt.WindowType.Popup)
        self.document_popup.setFrameShape(qt.QFrame.Shape.StyledPanel)
        self.document_popup.setAccessibleName('Open documents')
        popup_layout = qt.QVBoxLayout(self.document_popup)
        popup_layout.addWidget(qt.QLabel('Open documents'))
        self.document_list = qt.QListWidget()
        self.document_list.setObjectName('documentSwitchList')
        self.document_list.setStyleSheet('QListWidget#documentSwitchList::item { padding: 0px; margin: 0px; }')
        self.document_list.setMinimumWidth(350)
        self.document_list.setMaximumWidth(480)
        popup_layout.addWidget(self.document_list)
        self.buttons['documents'].hide()
        self.buttons['actions'].hide()

    def _button(self, key, title):
        button = ActivityButton(self) if key == 'actions' else qt.QToolButton(self)
        button.setIcon(qt.QIcon(DestinationIcon(key)))
        button.setIconSize(qt.QSize(26, 26))
        button.setFixedSize(46, 42)
        button.setCheckable(True)
        button.setAccessibleName(title)
        button.setToolTip(title)
        button.setText(title)
        button.setToolButtonStyle(qt.Qt.ToolButtonStyle.ToolButtonIconOnly)
        if key not in ('tools', 'documents'):
            button.clicked.connect(lambda checked=False, name=key: self.selected.emit(self.pages.get(name)))
        self.buttons[key] = button
        return button

    def refresh(self, tabs, core):
        core = {page: (order, name) for order, name, page in core}
        self.pages = {}
        self.tools_menu.clear()
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
            if key:
                self.pages[key] = page
            else:
                action = self.tools_menu.addAction(tabs.tabText(index))
                action.setData(page)
                action.setCheckable(True)
                action.setChecked(page is tabs.currentWidget())
                action.triggered.connect(lambda checked=False, target=page: self.selected.emit(target))
        for key in ('browser', 'hub', 'settings'):
            self.buttons[key].setVisible(key in self.pages)
        self.buttons['tools'].setVisible(bool(self.tools_menu.actions()))
        self.buttons['documents'].setVisible(bool(self.documents.count))
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
        if self.document_popup.isVisible():
            self._populate_documents()

    def set_current(self, page):
        is_tool = page is not None and page not in self.pages.values() and page is not self.documents
        for key, button in self.buttons.items():
            button.setChecked(is_tool if key == 'tools' else
                              page is (self.documents if key == 'documents' else self.pages.get(key)))
        for action in self.tools_menu.actions():
            action.setChecked(action.data() is page)

    def _populate_documents(self):
        self.document_list.clear()
        for window, label, tab, detached in self.documents.document_entries():
            item = qt.QListWidgetItem(self.document_list)
            row = qt.QWidget()
            layout = qt.QHBoxLayout(row)
            layout.setContentsMargins(6, 4, 6, 4)
            title = qt.QPushButton(label)
            title.setFlat(True)
            title.setStyleSheet('QPushButton { border: none; text-align: left; padding: 4px; }')
            title.setSizePolicy(qt.QSizePolicy.Policy.Ignored, qt.QSizePolicy.Policy.Preferred)
            path = getattr(tab, 'path', None) if tab is not None else window.windowFilePath() or getattr(window, 'path', None)
            title.setToolTip(label + (' — detached' if detached else '') + (f'\n{path}' if path else ''))
            title.clicked.connect(lambda checked=False, view=window, buffer=tab: self._open_document(view, tab=buffer))
            layout.addWidget(title, 1)
            if detached:
                back = qt.QPushButton('Bring back')
                back.clicked.connect(lambda checked=False, view=window, buffer=tab: self._open_document(view, tab=buffer, attach=True))
                layout.addWidget(back)
            item.setSizeHint(qt.QSize(0, max(40, row.sizeHint().height())))
            self.document_list.setItemWidget(item, row)
        self.document_list.setFixedHeight(min(420, max(80, self.document_list.count()*44+8)))

    def _open_document(self, window, *, attach=False, tab=None):
        self.document_popup.hide()
        if tab is not None:
            window.tabs.setCurrentWidget(tab)
        if attach:
            self.documents.attach(window)
        else:
            self.documents.present(window)

    def show_documents(self):
        self._populate_documents()
        button = self.buttons['documents']
        self.document_popup.adjustSize()
        self.document_popup.move(button.mapToGlobal(qt.QPoint(button.width()+8, 0)))
        self.document_popup.show()
