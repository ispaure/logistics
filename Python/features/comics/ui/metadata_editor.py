"""ComicRack-style metadata dialog; edit only fields the user changed."""

from pathlib import Path
from commonUtils.ui import pyside as qt
from features.comics.comicinfo import ComicInfoXML
from features.comics.library import ComicDocument


class Operation(qt.QThread):
    completed = qt.Signal(object, str)

    def __init__(self, callback, parent):
        super().__init__(parent)
        self.callback = callback

    def run(self):
        try:
            self.completed.emit(self.callback(), '')
        except Exception as error:
            self.completed.emit(None, str(error))


class MetadataEditor(qt.QDialog):
    saved = qt.Signal(object)

    def __init__(self, path, siblings=None, parent=None):
        super().__init__(parent)
        self.setWindowFlag(qt.Qt.WindowType.Window, True)
        self.resize(1160, 900)
        self.path = Path(path)
        self.siblings = list(siblings or [self.path])
        if self.path not in self.siblings:
            self.siblings.append(self.path)
        self.document = None
        self.busy = False
        self.pending_action = None
        self.editors = {}
        self.baseline = {}
        layout = qt.QVBoxLayout(self)
        self.tabs = qt.QTabWidget()
        layout.addWidget(self.tabs, 1)
        self._details_tab()
        self._plot_tab()
        self.message = qt.QLabel()
        self.message.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        buttons = qt.QHBoxLayout()
        self.previous_button = qt.QPushButton('Previous')
        self.next_button = qt.QPushButton('Next')
        self.previous_button.clicked.connect(lambda: self._navigate(-1))
        self.next_button.clicked.connect(lambda: self._navigate(1))
        buttons.addWidget(self.previous_button)
        buttons.addWidget(self.next_button)
        buttons.addStretch()
        self.ok_button = qt.QPushButton('OK')
        self.cancel_button = qt.QPushButton('Cancel')
        self.apply_button = qt.QPushButton('Apply')
        self.ok_button.setDefault(True)
        self.ok_button.clicked.connect(self._ok)
        self.cancel_button.clicked.connect(self.reject)
        self.apply_button.clicked.connect(self._save)
        for button in (self.ok_button, self.cancel_button, self.apply_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self._load(self.path)

    def _field(self, field, label, choices=None, multiline=False):
        box = qt.QWidget()
        layout = qt.QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        caption = qt.QLabel(label + ':')
        font = caption.font()
        font.setBold(True)
        caption.setFont(font)
        layout.addWidget(caption)
        if choices is not None:
            editor = qt.QComboBox()
            editor.setEditable(True)
            editor.addItem('', '')
            for text, value in choices:
                editor.addItem(text, value)
            editor.currentTextChanged.connect(self._update_buttons)
        elif multiline:
            editor = qt.QPlainTextEdit()
            editor.textChanged.connect(self._update_buttons)
        else:
            editor = qt.QLineEdit()
            editor.textChanged.connect(self._update_buttons)
        if field in ComicInfoXML.INTEGER_FIELDS:
            editor.setPlaceholderText('Unspecified')
            editor.setToolTip('Integer; blank means unspecified. -1 is the legacy unknown value.')
        if field in ('Number', 'AlternateNumber'):
            editor.setToolTip('Issue number is text: e.g. 1, 1A, 0.5 or ½.')
        if field in ('Writer', 'Penciller', 'Inker', 'Colorist', 'Letterer', 'CoverArtist',
                     'Editor', 'Translator', 'Genre', 'Tags', 'Characters', 'Teams', 'Locations'):
            editor.setToolTip('Separate multiple values with commas.')
        if field == 'LanguageISO':
            editor.setToolTip('Stored as a language tag, e.g. en, fr or zh-Hant. Custom tags are accepted.')
        self.editors[field] = editor
        layout.addWidget(editor, 1)
        return box

    def _combo(self, field, label):
        return self._field(field, label, [(('Yes (right to left)' if value == 'YesAndRightToLeft' else value), value)
                                        for value in ComicInfoXML.ENUMS[field]])

    def _library_only(self, label, field):
        box = qt.QWidget()
        layout = qt.QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        caption = qt.QLabel(label + ':')
        font = caption.font()
        font.setBold(True)
        caption.setFont(font)
        layout.addWidget(caption)
        editor = qt.QComboBox()
        editor.addItem('ComicRack library only')
        editor.setEnabled(False)
        editor.setToolTip(f'{field} is ComicRack library state, not a standard ComicInfo.xml field. '
                          'Existing XML extensions are preserved.')
        layout.addWidget(editor)
        return box

    def _details_tab(self):
        scroll = qt.QScrollArea()
        scroll.setWidgetResizable(True)
        page = qt.QWidget()
        grid = qt.QGridLayout(page)
        grid.setContentsMargins(24, 24, 24, 24)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(14)
        for col, stretch in enumerate((4, 1, 1, 1, 3)):
            grid.setColumnStretch(col, stretch)
        def add(field, label, row, col, span=1, choices=None):
            grid.addWidget(self._field(field, label, choices), row, col, 1, span)
        add('Series', 'Series', 0, 0)
        add('Volume', 'Volume', 0, 1)
        add('Number', 'Number', 0, 2)
        add('Count', 'of', 0, 3)
        add('Format', 'Format', 0, 4, choices=[(v, v) for v in ('TPB', 'HC', 'Single Issue', 'Web', 'Digital')])
        add('Title', 'Title', 1, 0)
        add('Year', 'Year', 1, 1)
        add('Month', 'Month', 1, 2)
        add('Day', 'Day', 1, 3)
        add('Publisher', 'Publisher', 1, 4, choices=[])
        add('AlternateSeries', 'Alternate Series or Storyline Title', 2, 0, 2)
        add('AlternateNumber', 'Number', 2, 2)
        add('AlternateCount', 'of', 2, 3)
        add('Imprint', 'Imprint', 2, 4, choices=[])
        add('StoryArc', 'Story Arc', 3, 0)
        add('SeriesGroup', 'Series Group', 3, 1, 3)
        grid.addWidget(self._library_only('Series complete', 'SeriesComplete'), 3, 4)
        grid.setRowMinimumHeight(4, 28)
        for row, left, right in ((5, 'Writer', 'Penciller'), (6, 'Inker', 'Colorist'),
                                  (7, 'Letterer', 'CoverArtist'), (8, 'Editor', 'Translator')):
            add(left, left, row, 0)
            add(right, 'Cover Artist' if right == 'CoverArtist' else right, row, 1, 3)
        grid.addWidget(self._combo('AgeRating', 'Age Rating'), 5, 4)
        grid.addWidget(self._combo('Manga', 'Manga'), 6, 4)
        languages = [('English', 'en'), ('French', 'fr'), ('Japanese', 'ja'),
                     ('Spanish', 'es'), ('German', 'de'), ('Italian', 'it'),
                     ('Chinese', 'zh'), ('Korean', 'ko'), ('Portuguese', 'pt')]
        add('LanguageISO', 'Language', 7, 4, choices=languages)
        grid.addWidget(self._combo('BlackAndWhite', 'Black and White'), 8, 4)
        grid.setRowMinimumHeight(9, 28)
        add('Genre', 'Genre', 10, 0, 4)
        add('Tags', 'Tags', 11, 0, 4)
        grid.addWidget(self._library_only('Proposed Values', 'EnableProposed'), 11, 4)
        grid.setRowStretch(12, 1)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, 'Details')

    def _plot_tab(self):
        page = qt.QWidget()
        grid = qt.QGridLayout(page)
        grid.setContentsMargins(24, 24, 24, 24)
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(16)
        text_tabs = qt.QTabWidget()
        for field in ('Summary', 'Notes', 'Review'):
            # The text editor fills each sub-tab, like the screenshot.
            editor = qt.QPlainTextEdit()
            editor.textChanged.connect(self._update_buttons)
            self.editors[field] = editor
            text_tabs.addTab(editor, field)
        grid.addWidget(text_tabs, 0, 0, 1, 2)
        grid.setRowStretch(0, 3)
        grid.addWidget(self._field('Characters', 'Characters', multiline=True), 1, 0, 3, 1)
        grid.addWidget(self._field('MainCharacterOrTeam', 'Main Character or Team'), 1, 1)
        grid.addWidget(self._field('Teams', 'Teams'), 2, 1)
        grid.addWidget(self._field('Locations', 'Locations'), 3, 1)
        grid.setRowMinimumHeight(4, 24)
        grid.addWidget(self._field('ScanInformation', 'Scan Information'), 5, 0)
        grid.addWidget(self._field('Web', 'Web'), 5, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.tabs.addTab(page, 'Plot && Notes')

    def _value(self, editor):
        if isinstance(editor, qt.QPlainTextEdit):
            return editor.toPlainText()
        if isinstance(editor, qt.QComboBox):
            index = editor.currentIndex()
            if index >= 0 and editor.currentText() == editor.itemText(index):
                return editor.itemData(index)
            return editor.currentText()
        return editor.text()

    def _changes(self):
        return {field: self._value(editor) for field, editor in self.editors.items()
                if self._value(editor) != self.baseline.get(field, '')}

    def _update_buttons(self):
        if not hasattr(self, 'apply_button'):
            return
        available = self.document is not None and not self.busy
        self.tabs.setEnabled(available)
        self.ok_button.setEnabled(available)
        self.apply_button.setEnabled(available and bool(self._changes()))
        self.cancel_button.setEnabled(not self.busy)
        index = self.siblings.index(self.path)
        self.previous_button.setEnabled(available and index > 0)
        self.next_button.setEnabled(available and index < len(self.siblings) - 1)

    def _operate(self, callback, finished):
        self.busy = True
        self._update_buttons()
        self.operation = Operation(callback, self)
        self.operation.completed.connect(finished)
        self.operation.finished.connect(self._finished)
        self.operation.start()

    def _finished(self):
        self.busy = False
        self.operation.deleteLater()
        self._update_buttons()
        action, self.pending_action = self.pending_action, None
        if action:
            action()

    def _load(self, path):
        self.path = path
        self.document = None
        self.setWindowTitle(f'Edit Metadata — {path.name}')
        self.message.setText('Reading ComicInfo.xml…')
        self._operate(lambda: ComicDocument(path), self._loaded)

    def _loaded(self, document, error):
        if error:
            self.message.setText(f'Cannot read metadata: {error}')
            return
        try:
            values = {field: document.info.get_field(field) for field in self.editors}
        except Exception as error:
            self.message.setText(f'Cannot read metadata: {error}')
            return
        for field, editor in self.editors.items():
            value = values[field]
            editor.blockSignals(True)
            if isinstance(editor, qt.QPlainTextEdit):
                editor.setPlainText(value)
            elif isinstance(editor, qt.QComboBox):
                index = editor.findData(value)
                if index < 0:
                    editor.addItem(value, value)  # Retain unrecognized legacy values.
                    index = editor.count() - 1
                editor.setCurrentIndex(index)
            else:
                editor.setText(value)
            editor.blockSignals(False)
        self.document = document
        # QPlainTextEdit normalizes line endings. Compare against displayed text
        # so untouched XML whitespace is never silently rewritten on another edit.
        self.baseline = {field: self._value(editor) for field, editor in self.editors.items()}
        self.message.setText('Only changed fields are saved; other XML metadata is retained.' if document.exists else
                             'No ComicInfo.xml yet. Apply or OK will create it when fields are changed.')

    def _save(self, after=None):
        if self.busy or self.document is None:
            return
        changes = self._changes()
        if not changes:
            if after:
                after()
            return
        try:
            candidate = ComicInfoXML.from_bytes(self.document.info.to_bytes())
            for field, value in changes.items():
                candidate.set_field(field, value)
            candidate.to_bytes()
        except Exception as error:
            qt.QMessageBox.warning(self, 'Check metadata', str(error))
            return
        document = self.document
        self.pending_action = after
        self.message.setText('Saving and verifying the comic archive…')
        def save():
            document.save(changes)
            return document
        self._operate(save, self._saved)

    def _saved(self, document, error):
        if error:
            self.pending_action = None
            self.message.setText(f'Could not save: {error}. Close and reopen to reload a changed archive.')
            qt.QMessageBox.warning(self, 'Metadata was not saved', error)
        else:
            self.document = document
            self.baseline = {field: self._value(editor) for field, editor in self.editors.items()}
            self.message.setText('Metadata saved.')
            self.saved.emit(self.path)

    def _ok(self):
        self._save(after=lambda: super(MetadataEditor, self).accept())

    def _leave(self, action):
        if self.busy:
            return
        if not self.document or not self._changes():
            action()
            return
        choice = qt.QMessageBox.question(self, 'Unsaved metadata', 'Save your changes before continuing?',
            qt.QMessageBox.StandardButton.Save | qt.QMessageBox.StandardButton.Discard |
            qt.QMessageBox.StandardButton.Cancel, qt.QMessageBox.StandardButton.Cancel)
        if choice == qt.QMessageBox.StandardButton.Save:
            self._save(after=action)
        elif choice == qt.QMessageBox.StandardButton.Discard:
            action()

    def _navigate(self, direction):
        index = self.siblings.index(self.path) + direction
        if 0 <= index < len(self.siblings):
            self._leave(lambda: self._load(self.siblings[index]))

    def reject(self):
        self._leave(lambda: super(MetadataEditor, self).reject())

    def closeEvent(self, event):
        event.ignore()
        self.reject()
