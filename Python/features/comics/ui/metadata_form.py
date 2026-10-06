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
        self._details_tab()
        self._plot_tab()

    def _field_changed(self, *args):
        self.changed.emit()

    def values(self):
        return {field: editor_value(editor) for field, editor in self.editors.items()}

    def changes(self):
        return {field: value for field, value in self.values().items()
                if value != self.baseline.get(field, '')}

    def load(self, info):
        # Read every exposed field before touching controls, so an ambiguous
        # field cannot leave a partially populated form.
        values = {field: info.get_field(field) for field in self.editors}
        for field, value in values.items():
            load_editor(self.editors[field], value)
        self.mark_saved()

    def mark_saved(self):
        # Qt normalizes text-area line endings. Baseline the displayed values
        # so another edit cannot silently rewrite untouched XML whitespace.
        self.baseline = self.values()

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
        layout.addWidget(caption)
        return box, layout, caption

    def _field(self, field, label, choices=None, multiline=False):
        box, layout, caption = self._field_box(label)
        editor = create_editor(field, self._field_changed, choices, multiline)
        editor.setMinimumWidth(0)
        if multiline:
            editor.setSizePolicy(qt.QSizePolicy.Policy.Expanding, qt.QSizePolicy.Policy.Ignored)
        else:
            box.setFixedHeight(caption.sizeHint().height() + 2 + INPUT_HEIGHT)
            editor.setFixedHeight(INPUT_HEIGHT)
            editor.setSizePolicy(qt.QSizePolicy.Policy.Ignored, qt.QSizePolicy.Policy.Fixed)
        self.editors[field] = editor
        layout.addWidget(editor, 1)
        return box

    def _combo(self, field, label):
        return self._field(field, label, [(('Yes (right to left)' if value == 'YesAndRightToLeft' else value), value)
                                        for value in ComicInfoXML.ENUMS[field]])

    def _library_only(self, label, field):
        box, layout, caption = self._field_box(label)
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
            editor = create_editor(field, self._field_changed, multiline=True)
            self.editors[field] = editor
            text_tabs.addTab(editor, field)
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

