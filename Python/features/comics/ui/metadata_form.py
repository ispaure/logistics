"""ComicRack-style tab layout and tracking of changed, visible metadata fields."""

from commonUtils.ui import pyside as qt
from features.comics.comicinfo import ComicInfoXML
from .metadata_widgets import create_editor, editor_value, load_editor

INPUT_HEIGHT = 22
DETAIL_COLUMN_WEIGHTS = (267, 74, 74, 74, 184)


class MetadataForm(qt.QTabWidget):
    changed = qt.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.editors = {}
        self.baseline = {}
        self.mixed = set()
        self.touched = set()
        self.captions = {}
        self.revert_buttons = {}
        self.clear_buttons = {}
        self.original_values = {}
        self._base_tooltips = {}
        self._normal_palettes = {}
        self._labels = {}
        self._details_tab()
        self._plot_tab()

    def _field_changed(self, field, *args):
        self.touched.add(field)
        self._refresh_field(field)
        self.changed.emit()

    def values(self):
        return {field: editor_value(editor) for field, editor in self.editors.items()}

    def changes(self):
        values = self.values()
        return {field: values[field] for field in self.touched
                if field in self.mixed or values[field] != self.baseline[field]}

    def load(self, info):
        self.load_values([{field: info.get_field(field) for field in self.editors}])

    def load_values(self, documents):
        if not documents:
            raise ValueError('No comic metadata to edit')
        self.original_values = {field: tuple(values[field] for values in documents) for field in self.editors}
        self.mixed = {field for field in self.editors
                      if any(values[field] != documents[0][field] for values in documents[1:])}
        self.touched.clear()
        for field, editor in self.editors.items():
            value = '' if field in self.mixed else documents[0][field]
            load_editor(editor, value)
        # Qt normalizes multiline whitespace. Compare with what was displayed
        # so untouched XML text is never rewritten by another field's edit.
        self.baseline = self.values()
        for field in self.editors:
            self._refresh_field(field)

    def revert_field(self, field):
        load_editor(self.editors[field], self.baseline[field])
        self.touched.discard(field)
        self._refresh_field(field)
        self.changed.emit()

    def clear_field(self, field):
        """An explicit clear is needed when a mixed field already displays blank."""
        load_editor(self.editors[field], '')
        self.touched.add(field)
        self._refresh_field(field)
        self.changed.emit()

    def _refresh_field(self, field):
        editor = self.editors[field]
        pending = field in self.changes()
        mixed = field in self.mixed and field not in self.touched
        palette = qt.QPalette(self._normal_palettes[field])
        if mixed:
            muted = palette.color(qt.QPalette.ColorGroup.Disabled, qt.QPalette.ColorRole.Text)
            palette.setColor(qt.QPalette.ColorRole.Text, muted)
        editor.setPalette(palette)
        placeholder = 'Multiple values — unchanged' if mixed else ''
        if isinstance(editor, (qt.QAbstractSpinBox, qt.QComboBox)):
            editor.lineEdit().setPlaceholderText(placeholder)
        else:
            editor.setPlaceholderText(placeholder)
        caption = self.captions[field]
        caption.setText(self._labels[field] + (': *' if pending else ':'))
        self.revert_buttons[field].setVisible(pending)
        self.clear_buttons[field].setVisible(mixed)
        distinct = list(dict.fromkeys(self.original_values.get(field, ())))
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
            editor.setSizePolicy(qt.QSizePolicy.Policy.Expanding, qt.QSizePolicy.Policy.Ignored)
        else:
            box.setFixedHeight(caption.sizeHint().height() + 2 + INPUT_HEIGHT)
            editor.setFixedHeight(INPUT_HEIGHT)
            editor.setSizePolicy(qt.QSizePolicy.Policy.Ignored, qt.QSizePolicy.Policy.Fixed)
        self._register(field, editor, label, caption, header)
        layout.addWidget(editor, 1)
        return box

    def _combo(self, field, label):
        return self._field(field, label, [(('Yes (right to left)' if value == 'YesAndRightToLeft' else value), value)
                                        for value in ComicInfoXML.ENUMS[field]])

    def _library_only(self, label, field):
        box, layout, caption, header = self._field_box(label)
        box.setFixedHeight(caption.sizeHint().height() + 2 + INPUT_HEIGHT)
        editor = qt.QComboBox()
        editor.addItem('ComicRack library only')
        editor.setFixedHeight(INPUT_HEIGHT)
        editor.setSizePolicy(qt.QSizePolicy.Policy.Ignored, qt.QSizePolicy.Policy.Fixed)
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

