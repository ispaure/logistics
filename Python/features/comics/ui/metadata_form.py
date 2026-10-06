"""Compact tab layout and tracking of changed, visible metadata fields."""

from commonUtils.ui import pyside as qt
from features.comics.comicinfo import ComicInfoXML
from features.comics.edit_state import MetadataEditState
from features.comics.catalog import LIST_FIELDS, split_values
from .value_popup import ValuePopup
from .metadata_widgets import create_editor, editor_value, load_editor

INPUT_HEIGHT = 22
DETAIL_COLUMN_WEIGHTS = (267, 74, 74, 74, 184)


class MetadataForm(qt.QTabWidget):
    changed = qt.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.suggestions = {}
        self.list_buttons = {}
        self.popup = None
        self.editors = {}
        self.state = MetadataEditState()
        self.captions = {}
        self.revert_buttons = {}
        self.clear_buttons = {}
        self._base_tooltips = {}
        self._combo_choices = {}
        self._normal_palettes = {}
        self._labels = {}
        self._details_tab()
        self._plot_tab()

    def set_suggestions(self, suggestions):
        self.suggestions = suggestions
        # Updating suggestions must never change displayed values or pending edits.
        for field in ('Publisher', 'Imprint', 'Format'):
            editor = self.editors[field]
            value = editor_value(editor)
            blocker = qt.QSignalBlocker(editor)
            try:
                editor.clear()
                for text, data in self._combo_choices[field]:
                    editor.addItem(text, data)
                existing = {editor.itemData(i) for i in range(editor.count())}
                for suggestion in suggestions.get(field, []):
                    if suggestion not in existing:
                        editor.addItem(suggestion, suggestion)
                load_editor(editor, value)
            finally:
                blocker.unblock()

    def open_list(self, field):
        if field not in self.state.fields:
            return
        if self.popup is not None:
            self.popup.close()
            self.popup.deleteLater()
        entry = self.state.fields[field]
        choices = list(self.suggestions.get(field, []))
        for original in entry.originals:
            choices.extend(split_values(original))
        self.popup = ValuePopup(editor_value(self.editors[field]), choices,
                                self._labels[field], entry.mixed and not entry.changed, self)
        self.popup.value_changed.connect(lambda value: self.apply_pending({field: value}))
        self.popup.show_at(self.list_buttons[field])

    def _field_changed(self, field, *args):
        self.state.fields[field].edit(editor_value(self.editors[field]))
        self._refresh_field(field)
        self.changed.emit()

    def values(self):
        return {field: editor_value(editor) for field, editor in self.editors.items()}

    def changes(self):
        return self.state.changes()

    def load(self, info):
        self.load_values([{field: info.get_field(field) for field in self.editors}])

    def load_values(self, documents):
        self.state.reset(documents, self.editors)
        for field, editor in self.editors.items():
            entry = self.state.fields[field]
            load_editor(editor, entry.baseline)
            # Qt normalizes text-area whitespace. Preserve the loaded original
            # XML until this field is explicitly changed.
            entry.baseline = editor_value(editor)
        for field in self.editors:
            self._refresh_field(field)

    def apply_pending(self, changes):
        for field, value in changes.items():
            load_editor(self.editors[field], value)
            self.state.fields[field].edit(value)
            self._refresh_field(field)
        self.changed.emit()

    def revert_field(self, field):
        entry = self.state.fields[field]
        load_editor(self.editors[field], entry.baseline)
        self.state.revert(field)
        self._refresh_field(field)
        self.changed.emit()

    def clear_field(self, field):
        """An explicit clear is needed when a mixed field already displays blank."""
        self.apply_pending({field: ''})

    def _refresh_field(self, field):
        editor = self.editors[field]
        entry = self.state.fields[field]
        pending = entry.changed
        mixed = entry.mixed and not pending
        palette = qt.QPalette(self._normal_palettes[field])
        if mixed:
            muted = palette.color(qt.QPalette.ColorGroup.Disabled, qt.QPalette.ColorRole.Text)
            palette.setColor(qt.QPalette.ColorRole.Text, muted)
        editor.setPalette(palette)
        placeholder = ('Mixed' if isinstance(editor, qt.QAbstractSpinBox) else 'Multiple values — unchanged') if mixed else ''
        if isinstance(editor, (qt.QAbstractSpinBox, qt.QComboBox)):
            editor.lineEdit().setPlaceholderText(placeholder)
        else:
            editor.setPlaceholderText(placeholder)
        caption = self.captions[field]
        caption.setText(self._labels[field] + (': *' if pending else ':'))
        self.revert_buttons[field].setVisible(pending)
        self.clear_buttons[field].setVisible(mixed)
        distinct = list(dict.fromkeys(entry.originals))
        if mixed:
            examples = ', '.join(repr(value[:80]) if value else '(blank)' for value in distinct[:4])
            suffix = '…' if len(distinct) > 4 else ''
            hint = f'Multiple values: {examples}{suffix}. Leave untouched to preserve them; × clears this field for all comics.'
        elif pending:
            hint = 'Pending: apply this value to every selected comic. Revert restores the original value(s).'
        else:
            hint = ''
        editor.setToolTip(' '.join(part for part in (self._base_tooltips[field], hint) if part))
        editor.setProperty('mixedValue', mixed)
        editor.setProperty('pendingChange', pending)

    def _register(self, field, editor, label, caption, header):
        self.editors[field] = editor
        self.captions[field] = caption
        self._labels[field] = label
        self._normal_palettes[field] = qt.QPalette(editor.palette())
        self._base_tooltips[field] = editor.toolTip()
        if isinstance(editor, qt.QComboBox):
            self._combo_choices[field] = [(editor.itemText(i), editor.itemData(i)) for i in range(editor.count())]
        clear = qt.QToolButton()
        clear.setText('×')
        clear.setToolTip('Clear this field in every selected comic (pending until Apply)')
        clear.setAccessibleName(f'Clear {label} in all selected comics')
        clear.setFixedSize(18, 16)
        clear.hide()
        clear.clicked.connect(lambda: self.clear_field(field))
        header.addWidget(clear)
        self.clear_buttons[field] = clear
        revert = qt.QToolButton()
        revert.setText('↶')
        revert.setToolTip('Revert this field to its original value(s)')
        revert.setAccessibleName(f'Revert {label}')
        revert.setFixedSize(18, 16)
        revert.hide()
        revert.clicked.connect(lambda: self.revert_field(field))
        header.addWidget(revert)
        self.revert_buttons[field] = revert

    def _field_box(self, label):
        box = qt.QWidget()
        box.setFont(self.font())
        layout = qt.QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        caption = qt.QLabel(label + ':')
        font = caption.font()
        font.setBold(True)
        caption.setFont(font)
        header = qt.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(0)
        header.addWidget(caption, 1)
        layout.addLayout(header)
        return box, layout, caption, header

    def _field(self, field, label, choices=None, multiline=False):
        box, layout, caption, header = self._field_box(label)
        editor = create_editor(field, lambda *args: self._field_changed(field), choices, multiline)
        editor.setMinimumWidth(0)
        if multiline:
            editor.setSizePolicy(qt.QSizePolicy.Policy.Expanding, qt.QSizePolicy.Policy.Expanding)
            editor.setMinimumHeight(0)
        else:
            box.setFixedHeight(caption.sizeHint().height() + 2 + INPUT_HEIGHT)
            editor.setFixedHeight(INPUT_HEIGHT)
            editor.setSizePolicy(qt.QSizePolicy.Policy.Ignored, qt.QSizePolicy.Policy.Fixed)
        self._register(field, editor, label, caption, header)
        if field in LIST_FIELDS:
            row = qt.QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(2)
            row.addWidget(editor, 1)
            button = qt.QToolButton()
            button.setText('◇')
            button.setAccessibleName(f'Edit {label} list')
            button.setToolTip('Edit values using Lists, Check or Text')
            button.setFixedWidth(20)
            if multiline:
                button.setSizePolicy(qt.QSizePolicy.Policy.Fixed, qt.QSizePolicy.Policy.Expanding)
            else:
                button.setFixedHeight(INPUT_HEIGHT)
            button.clicked.connect(lambda: self.open_list(field))
            row.addWidget(button)
            self.list_buttons[field] = button
            layout.addLayout(row, 1)
        else:
            layout.addWidget(editor, 1)
        return box

    def _combo(self, field, label):
        return self._field(field, label, [(('Yes (right to left)' if value == 'YesAndRightToLeft' else value), value)
                                        for value in ComicInfoXML.ENUMS[field]])

    def _library_only(self, label, field):
        box, layout, caption, header = self._field_box(label)
        box.setFixedHeight(caption.sizeHint().height() + 2 + INPUT_HEIGHT)
        editor = qt.QComboBox()
        editor.addItem('Library-only field')
        editor.setFixedHeight(INPUT_HEIGHT)
        editor.setSizePolicy(qt.QSizePolicy.Policy.Ignored, qt.QSizePolicy.Policy.Fixed)
        editor.setEnabled(False)
        editor.setToolTip(f'{field} is application library state, not a standard ComicInfo.xml field. '
                          'Existing XML extensions are preserved.')
        layout.addWidget(editor)
        return box

    def _details_tab(self):
        scroll = qt.QScrollArea()
        scroll.setWidgetResizable(True)
        page = qt.QWidget()
        grid = qt.QGridLayout(page)
        grid.setContentsMargins(18, 18, 18, 18)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(5)
        for col, stretch in enumerate(DETAIL_COLUMN_WEIGHTS):
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
        grid.setRowMinimumHeight(4, 32)
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
        grid.setRowMinimumHeight(9, 31)
        add('Genre', 'Genre', 10, 0, 4)
        add('Tags', 'Tags', 11, 0, 4)
        grid.addWidget(self._library_only('Proposed Values', 'EnableProposed'), 11, 4)
        grid.setRowStretch(12, 1)
        scroll.setWidget(page)
        self.addTab(scroll, 'Details')

    def _plot_tab(self):
        page = qt.QWidget()
        grid = qt.QGridLayout(page)
        grid.setContentsMargins(18, 18, 18, 18)
        grid.setHorizontalSpacing(22)
        grid.setVerticalSpacing(10)
        text_tabs = qt.QTabWidget()
        for field in ('Summary', 'Notes', 'Review'):
            # The text editor fills each sub-tab, like the screenshot.
            editor = create_editor(field, lambda *args, name=field: self._field_changed(name), multiline=True)
            box, layout, caption, header = self._field_box(field)
            self._register(field, editor, field, caption, header)
            layout.addWidget(editor, 1)
            text_tabs.addTab(box, field)
        grid.addWidget(text_tabs, 0, 0, 1, 2)
        grid.setRowStretch(0, 3)
        grid.setRowStretch(1, 0)
        grid.setRowStretch(2, 0)
        grid.setRowStretch(3, 0)
        grid.addWidget(self._field('Characters', 'Characters', multiline=True), 1, 0, 3, 1)
        grid.addWidget(self._field('MainCharacterOrTeam', 'Main Character or Team'), 1, 1)
        grid.addWidget(self._field('Teams', 'Teams'), 2, 1)
        grid.addWidget(self._field('Locations', 'Locations'), 3, 1)
        grid.setRowMinimumHeight(4, 18)
        grid.addWidget(self._field('ScanInformation', 'Scan Information'), 5, 0)
        grid.addWidget(self._field('Web', 'Web'), 5, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.addTab(page, 'Plot && Notes')

