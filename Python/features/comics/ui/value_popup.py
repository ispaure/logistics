"""Floating list/check/text helpers for comma-separated metadata fields."""

from commonUtils.ui import pyside as qt
from features.comics.catalog import split_values


class ValuePopup(qt.QFrame):
    value_changed = qt.Signal(str)

    def __init__(self, value, suggestions, label, mixed=False, parent=None):
        super().__init__(parent, qt.Qt.WindowType.Popup)
        self.setFrameShape(qt.QFrame.Shape.StyledPanel)
        self.setAccessibleName(f'Edit {label} values')
        self.resize(460, 380)
        self.values = split_values(value)
        self.known = set(suggestions) | set(self.values)
        self.syncing = False
        layout = qt.QVBoxLayout(self)
        title = qt.QLabel(label)
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        if mixed:
            hint = qt.QLabel('Mixed values. Changes here replace this field in all selected comics.')
            hint.setWordWrap(True)
            layout.addWidget(hint)
        self.search = qt.QLineEdit()
        self.search.setPlaceholderText('Filter suggestions…')
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)
        self.tabs = qt.QTabWidget()
        layout.addWidget(self.tabs, 1)
        lists = qt.QWidget()
        grid = qt.QGridLayout(lists)
        self.selected = qt.QListWidget()
        self.available = qt.QListWidget()
        for widget in (self.selected, self.available):
            widget.setSelectionMode(qt.QAbstractItemView.SelectionMode.ExtendedSelection)
        grid.addWidget(qt.QLabel('Selected values'), 0, 0)
        grid.addWidget(qt.QLabel('Available values'), 0, 2)
        grid.addWidget(self.selected, 1, 0)
        grid.addWidget(self.available, 1, 2)
        arrows = qt.QVBoxLayout()
        for caption, callback, hint in (('<<', lambda: self._add(True), 'Add all filtered suggestions'),
                                        ('<', self._add, 'Add selected suggestions'),
                                        ('>', self._remove, 'Remove selected values'),
                                        ('>>', self._clear, 'Remove all values')):
            button = qt.QPushButton(caption)
            button.setFixedWidth(42)
            button.setToolTip(hint)
            button.clicked.connect(lambda checked=False, action=callback: action())
            arrows.addWidget(button)
        grid.addLayout(arrows, 1, 1)
        self.available.itemDoubleClicked.connect(lambda item: self._add())
        self.selected.itemDoubleClicked.connect(lambda item: self._remove())
        self.tabs.addTab(lists, 'Lists')
        self.checks = qt.QListWidget()
        self.checks.itemChanged.connect(self._checked)
        self.tabs.addTab(self.checks, 'Check')
        self.text = qt.QPlainTextEdit()
        self.text.setPlaceholderText('One value per line, or separate values with commas')
        self.text.textChanged.connect(self._text_changed)
        self.tabs.addTab(self.text, 'Text')
        self.tabs.currentChanged.connect(lambda index: self._sync())
        entry = qt.QHBoxLayout()
        self.new_value = qt.QLineEdit()
        self.new_value.setPlaceholderText('Add a new value…')
        add = qt.QPushButton('Add')
        add.clicked.connect(self._new)
        self.new_value.returnPressed.connect(self._new)
        entry.addWidget(self.new_value, 1)
        entry.addWidget(add)
        layout.addLayout(entry)
        footer = qt.QLabel('Changes stay pending until Apply or OK. Click outside to close.')
        footer.setWordWrap(True)
        layout.addWidget(footer)
        self._sync()

    def show_at(self, anchor):
        point = anchor.mapToGlobal(qt.QPoint(0, anchor.height()))
        screen = anchor.screen().availableGeometry()
        x = max(screen.left(), min(point.x(), screen.right() - self.width() + 1))
        y = point.y() if point.y() + self.height() <= screen.bottom() else point.y() - anchor.height() - self.height()
        self.move(x, max(screen.top(), y))
        self.show()
        self.search.setFocus()

    def _sync(self):
        self.syncing = True
        try:
            self.selected.clear()
            self.selected.addItems(self.values)
            self.available.clear()
            self.checks.clear()
            for value in sorted(self.known, key=lambda text: (text.casefold(), text)):
                if value not in self.values:
                    self.available.addItem(value)
                item = qt.QListWidgetItem(value)
                item.setFlags(item.flags() | qt.Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(qt.Qt.CheckState.Checked if value in self.values else qt.Qt.CheckState.Unchecked)
                self.checks.addItem(item)
            self.text.setPlainText('\n'.join(self.values))
            self._filter()
        finally:
            self.syncing = False

    def _filter(self, *args):
        query = self.search.text().casefold()
        for widget in (self.available, self.checks):
            for index in range(widget.count()):
                item = widget.item(index)
                item.setHidden(query not in item.text().casefold())

    def _change(self, values, sync=True):
        values = list(dict.fromkeys(values))
        if values == self.values:
            return
        self.values = values
        self.known.update(values)
        self.value_changed.emit(', '.join(values))
        if sync:
            self._sync()

    def _add(self, all_visible=False):
        items = ([self.available.item(i) for i in range(self.available.count())
                  if not self.available.item(i).isHidden()] if all_visible else self.available.selectedItems())
        self._change(self.values + [item.text() for item in items])

    def _remove(self):
        removed = {item.text() for item in self.selected.selectedItems()}
        self._change([value for value in self.values if value not in removed])

    def _clear(self):
        if self.values:
            self._change([])
        else:
            self.value_changed.emit('')  # An explicit clear also replaces untouched mixed values.

    def _new(self):
        self._change(self.values + split_values(self.new_value.text()))
        self.new_value.clear()

    def _checked(self, item):
        if self.syncing:
            return
        values = list(self.values)
        if item.checkState() == qt.Qt.CheckState.Checked:
            if item.text() not in values:
                values.append(item.text())
        elif item.text() in values:
            values.remove(item.text())
        self._change(values, sync=False)

    def _text_changed(self):
        if not self.syncing:
            self._change(split_values(self.text.toPlainText()), sync=False)
