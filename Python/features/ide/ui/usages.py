"""Non-modal, editor-anchored usage results with bounded source previews."""
from pathlib import Path
from shiboken6 import isValid
from commonUtils.ui import pyside as qt
from commonUtils.persistence.text import read_text_file


def position_editor_popup(popup, origin, width, height):
    """Confine an editor popup to its host window and available screen."""
    bounds = origin.window().frameGeometry()
    screen = origin.screen()
    if screen:
        bounds = bounds.intersected(screen.availableGeometry())
    width, height = min(width, max(1, bounds.width() - 24)), min(height, max(1, bounds.height() - 24))
    popup.setMinimumSize(0, 0)
    popup.resize(width, height)
    if hasattr(origin, 'viewport') and hasattr(origin, 'cursorRect'):
        anchor = origin.viewport().mapToGlobal(origin.cursorRect().bottomLeft()) + qt.QPoint(0, 6)
    else:
        anchor = origin.mapToGlobal(qt.QPoint(12, 12))
    x = max(bounds.left() + 12, min(anchor.x(), bounds.right() - width - 11))
    y = max(bounds.top() + 12, min(anchor.y(), bounds.bottom() - height - 11))
    popup.move(x, y)
    return width, height


def usage_previews(targets, source_path, source_code):
    """Run with the analysis worker, never perform file reads in popup painting."""
    texts = {Path(source_path).resolve(): source_code.splitlines()}
    previews = []
    for file, line, column, _ in targets:
        path = Path(file).resolve()
        if path not in texts:
            try:
                texts[path] = (read_text_file(path).text.splitlines()
                               if path.stat().st_size <= 1024 * 1024 else [])
            except (OSError, ValueError):
                texts[path] = []
        lines = texts[path]
        text = lines[line - 1] if 0 < line <= len(lines) else 'Source preview unavailable'
        start = max(0, column - 80)
        previews.append(('…' if start else '') + text[start:start + 300].strip())
    return previews


class UsagePopup(qt.QFrame):
    def __init__(self, parent):
        super().__init__(parent, qt.Qt.WindowType.Popup)
        self.setObjectName('ideUsagePopup')
        self.setAccessibleName('Python usages')
        self.setStyleSheet('''
            QFrame#ideUsagePopup { background: palette(window); border: 1px solid palette(mid); border-radius: 8px; }
            QFrame#ideUsagePopup QTreeWidget { background: palette(window); border: none; }
            QFrame#ideUsagePopup QTreeWidget::item { padding: 3px 4px; }
            QFrame#ideUsagePopup QTreeWidget::item:selected { background: palette(highlight); color: palette(highlighted-text); }
            QLabel#usageTitle { font-weight: bold; }
        ''')
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        header = qt.QHBoxLayout()
        self.title = qt.QLabel()
        self.title.setObjectName('usageTitle')
        header.addWidget(self.title, 1)
        self.count = qt.QLabel()
        header.addWidget(self.count)
        close = qt.QToolButton()
        close.setText('×')
        close.setAccessibleName('Close usages')
        close.clicked.connect(self.hide)
        header.addWidget(close)
        layout.addLayout(header)
        self.filter = qt.QLineEdit()
        self.filter.setPlaceholderText('Filter usages by file or code…')
        self.filter.setAccessibleName('Filter usages')
        self.filter.textChanged.connect(self.filter_rows)
        self.filter.installEventFilter(self)
        layout.addWidget(self.filter)
        self.scope = qt.QLabel('Project files')
        layout.addWidget(self.scope)
        self.tree = qt.QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(['File', 'Line', 'Code'])
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(qt.QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tree.setTextElideMode(qt.Qt.TextElideMode.ElideRight)
        self.tree.setAccessibleName('Usage locations with source previews')
        self.tree.itemClicked.connect(self.choose)
        self.tree.installEventFilter(self)
        layout.addWidget(self.tree, 1)
        self.empty = qt.QLabel('No static usages found in this project.')
        layout.addWidget(self.empty)
        layout.addWidget(qt.QLabel('↑↓ to select · Enter to open · Esc or click outside to close'))
        self.on_choose = None
        self.origin = None

    def filter_rows(self, text):
        query = text.casefold()
        visible = []
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            matches = query in (item.toolTip(0) + ' ' + item.text(2)).casefold()
            item.setHidden(not matches)
            if matches:
                visible.append(item)
        self.empty.setVisible(not visible)
        self.empty.setText('No matching usages.' if self.tree.topLevelItemCount() else
                           'No static usages found in this project.')
        if visible and (self.tree.currentItem() is None or self.tree.currentItem().isHidden()):
            self.tree.setCurrentItem(visible[0])

    def choose(self, item, column=0):
        if item is None or item.isHidden():
            return
        target = item.data(0, qt.Qt.ItemDataRole.UserRole)
        callback = self.on_choose
        self.hide()
        if callback:
            callback(target)

    def showEvent(self, event):
        qt.QApplication.instance().installEventFilter(self)
        super().showEvent(event)

    def hideEvent(self, event):
        qt.QApplication.instance().removeEventFilter(self)
        super().hideEvent(event)

    def eventFilter(self, watched, event):
        if event.type() == qt.QEvent.Type.MouseButtonPress and self.isVisible():
            point = self.mapFromGlobal(event.globalPosition().toPoint())
            if not self.rect().contains(point):
                self.hide()
        if (event.type() == qt.QEvent.Type.ApplicationDeactivate
                or event.type() == qt.QEvent.Type.Hide and watched in (self.parentWidget(), self.origin)):
            self.hide()
        if event.type() == qt.QEvent.Type.KeyPress and self.isVisible():
            if event.key() == qt.Qt.Key.Key_Escape:
                self.hide()
                if self.origin is not None and isValid(self.origin):
                    self.origin.setFocus()
                return True
            if event.key() in (qt.Qt.Key.Key_Return, qt.Qt.Key.Key_Enter):
                self.choose(self.tree.currentItem())
                return True
            if watched is self.filter and event.key() in (qt.Qt.Key.Key_Down, qt.Qt.Key.Key_Up):
                self.tree.setFocus()
                return True
        return super().eventFilter(watched, event)

    def origin_destroyed(self):
        self.origin = None
        self.hide()

    def present(self, origin, project, targets, previews, symbol, on_choose):
        if self.origin is not None and isValid(self.origin):
            self.origin.textChanged.disconnect(self.hide)
            self.origin.cursorPositionChanged.disconnect(self.hide)
            self.origin.destroyed.disconnect(self.origin_destroyed)
        self.origin = origin
        origin.textChanged.connect(self.hide)
        origin.cursorPositionChanged.connect(self.hide)
        origin.destroyed.connect(self.origin_destroyed)
        self.on_choose = on_choose
        self.tree.clear()
        self.filter.clear()
        self.title.setText('Usages of ' + symbol)
        noun = 'usage' if len(targets) == 1 else 'usages'
        self.count.setText(f'{len(targets)} {noun}' + (' (limit)' if len(targets) == 200 else ''))
        self.scope.setText('Project files · ' + project.name)
        font = qt.QFontDatabase.systemFont(qt.QFontDatabase.SystemFont.FixedFont)
        icon = self.style().standardIcon(qt.QStyle.StandardPixmap.SP_FileIcon)
        for target, preview in zip(targets, previews):
            file, line, column, name = target
            item = qt.QTreeWidgetItem([Path(file).name, str(line), preview])
            item.setIcon(0, icon)
            item.setData(0, qt.Qt.ItemDataRole.UserRole, target)
            try:
                relative = Path(file).resolve().relative_to(project.root).as_posix()
            except ValueError:
                relative = file
            item.setToolTip(0, relative)
            item.setToolTip(2, preview)
            item.setTextAlignment(1, qt.Qt.AlignmentFlag.AlignRight | qt.Qt.AlignmentFlag.AlignVCenter)
            item.setForeground(1, self.palette().color(qt.QPalette.ColorRole.PlaceholderText))
            item.setFont(2, font)
            self.tree.addTopLevelItem(item)
        self.filter_rows('')
        # Stay over the application, including near the editor's bottom/right edge.
        width, height = position_editor_popup(self, origin, 900, min(560, 175 + max(1, min(10, len(targets))) * 34))
        self.tree.setColumnWidth(0, min(250, width // 3))
        self.tree.setColumnWidth(1, 55)
        self.tree.header().setStretchLastSection(True)
        self.show()
        self.tree.setFocus()
