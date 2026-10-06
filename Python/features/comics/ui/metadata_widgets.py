"""Metadata input controls and lossless conversion between widgets and XML text."""

from decimal import Decimal, InvalidOperation
from commonUtils.ui import pyside as qt
from features.comics.comicinfo import ComicInfoXML


class OptionalIntegerSpinBox(qt.QSpinBox):
    """Numeric input with a blank state and lossless untouched legacy values."""

    def __init__(self, maximum, parent=None):
        super().__init__(parent)
        self.setRange(-1, maximum)
        self.setKeyboardTracking(False)
        self._original = ''
        self._edited = False
        self.valueChanged.connect(self._mark_edited)
        self.lineEdit().textEdited.connect(self._mark_edited)

    def _mark_edited(self, *args):
        self._edited = True

    def textFromValue(self, value):
        return '' if value == -1 else str(value)

    def load_text(self, text):
        try:
            number = int(text) if text else -1
        except ValueError:
            number = -1
        self.setValue(number)
        # Keep the original spelling (including -1 or unsupported legacy text).
        # The validator still rejects non-numeric typing and pasted content.
        self.lineEdit().setText(text)
        self._original = text
        self._edited = False

    def metadata_value(self):
        if not self._edited:
            return self._original
        return self.lineEdit().text().strip()

    def stepBy(self, steps):
        self._edited = True
        if not self.lineEdit().text().strip() and steps > 0:
            self.setValue(min(steps, self.maximum()))
        else:
            super().stepBy(steps)
        self.lineEdit().setText(self.textFromValue(self.value()))


class IssueNumberSpinBox(qt.QAbstractSpinBox):
    """Offer number arrows while retaining ComicInfo's string issue numbers."""

    def setText(self, text):
        self.lineEdit().setText(text)

    def _number(self):
        try:
            number = Decimal(self.text()) if self.text() else Decimal(0)
            return number if number.is_finite() else None
        except InvalidOperation:
            return None

    def stepEnabled(self):
        flags = qt.QAbstractSpinBox.StepEnabledFlag
        return flags.StepUpEnabled | flags.StepDownEnabled if self._number() is not None else flags.StepNone

    def stepBy(self, steps):
        number = self._number()
        if number is not None:
            self.lineEdit().setText(format(number + steps, 'f'))
            self.lineEdit().textEdited.emit(self.text())



def create_editor(field, changed, choices=None, multiline=False):
    """Create a field control with its change signal and schema-specific hint."""
    if choices is not None:
        editor = qt.QComboBox()
        editor.setEditable(True)
        editor.addItem('', '')
        for text, value in choices:
            editor.addItem(text, value)
        editor.currentTextChanged.connect(changed)
    elif field in ComicInfoXML.INTEGER_FIELDS:
        editor = OptionalIntegerSpinBox(ComicInfoXML.INTEGER_MAXIMUMS[field])
        editor.valueChanged.connect(changed)
        editor.lineEdit().textEdited.connect(changed)
    elif field in ('Number', 'AlternateNumber'):
        editor = IssueNumberSpinBox()
        editor.lineEdit().textEdited.connect(changed)
    elif multiline:
        editor = qt.QPlainTextEdit()
        editor.textChanged.connect(changed)
    else:
        editor = qt.QLineEdit()
        editor.textChanged.connect(changed)
    if field in ComicInfoXML.INTEGER_FIELDS:
        editor.setToolTip('Integer; blank means unspecified. -1 is the legacy unknown value.')
    elif field in ('Number', 'AlternateNumber'):
        editor.setToolTip('Issue number is text: e.g. 1, 1A, 0.5 or ½.')
    elif field in ('Writer', 'Penciller', 'Inker', 'Colorist', 'Letterer', 'CoverArtist',
                   'Editor', 'Translator', 'Genre', 'Tags', 'Characters', 'Teams', 'Locations'):
        editor.setToolTip('Separate multiple values with commas.')
    elif field == 'LanguageISO':
        editor.setToolTip('Stored as a language tag, e.g. en, fr or zh-Hant. Custom tags are accepted.')
    return editor


def editor_value(editor):
    """Read displayed text without normalizing an untouched integer sentinel."""
    if isinstance(editor, OptionalIntegerSpinBox):
        return editor.metadata_value()
    if isinstance(editor, qt.QPlainTextEdit):
        return editor.toPlainText()
    if isinstance(editor, qt.QComboBox):
        index = editor.currentIndex()
        if index >= 0 and editor.currentText() == editor.itemText(index):
            return editor.itemData(index)
        return editor.currentText()
    return editor.text()


def load_editor(editor, value):
    """Populate a control without emitting changes or dropping legacy choices."""
    blocker = qt.QSignalBlocker(editor)
    try:
        if isinstance(editor, OptionalIntegerSpinBox):
            editor.load_text(value)
        elif isinstance(editor, qt.QPlainTextEdit):
            editor.setPlainText(value)
        elif isinstance(editor, qt.QComboBox):
            index = editor.findData(value)
            if index < 0:
                editor.addItem(value, value)
                index = editor.count() - 1
            editor.setCurrentIndex(index)
        else:
            editor.setText(value)
    finally:
        blocker.unblock()
