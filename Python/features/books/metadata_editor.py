"""Explicit-save dialog for Dublin Core metadata stored inside the EPUB."""
from commonUtils.ui import pyside as qt
from .metadata import EDITABLE

LABELS = {'title': 'Title', 'creator': 'Authors (one per line)', 'language': 'Language (e.g. en)',
          'publisher': 'Publisher', 'subject': 'Tags (one per line)', 'description': 'Description'}


class MetadataEditor(qt.QDialog):
    def __init__(self, book, parent=None, *, save_handler=None):
        super().__init__(parent)
        self.save_handler = save_handler
        self.setWindowTitle('Edit EPUB metadata')
        self.resize(650, 680)
        layout = qt.QVBoxLayout(self)
        note = qt.QLabel('Save updates this EPUB directly. An original backup is kept beside the book. '
                        'Chapters, images and other metadata are preserved.')
        note.setWordWrap(True)
        layout.addWidget(note)
        form = qt.QFormLayout()
        self.fields = {}
        self.initial = {name: book.values(name) for name in EDITABLE}
        for name in EDITABLE:
            multiline = name in ('creator', 'subject', 'description')
            field = qt.QPlainTextEdit() if multiline else qt.QLineEdit()
            value = ('\n'.join(self.initial[name]) if name in ('creator', 'subject')
                     else next(iter(self.initial[name]), ''))
            if multiline:
                field.setPlainText(value)
                field.setMaximumHeight(170 if name == 'description' else 75)
            else:
                field.setText(value)
            field.setAccessibleName(LABELS[name])
            self.fields[name] = field
            form.addRow(LABELS[name], field)
        identifiers = qt.QLabel('\n'.join(book.values('identifier')) or 'No identifier')
        identifiers.setTextFormat(qt.Qt.TextFormat.PlainText)
        identifiers.setWordWrap(True)
        identifiers.setSizePolicy(qt.QSizePolicy.Policy.Preferred, qt.QSizePolicy.Policy.Maximum)
        form.addRow('Identifiers (preserved)', identifiers)
        layout.addLayout(form)
        self.error = qt.QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = qt.QDialogButtonBox(qt.QDialogButtonBox.StandardButton.Save | qt.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def changes(self):
        changes = {}
        for name, field in self.fields.items():
            value = field.toPlainText() if isinstance(field, qt.QPlainTextEdit) else field.text()
            if name in ('creator', 'subject'):
                values = value.splitlines()
            else:
                # Editing the primary title/language must preserve additional
                # translated values. Unrelated saves should not collapse them.
                values = [value] + self.initial[name][1:]
            values = [value.strip() for value in values if value.strip()]
            if values != self.initial[name]:
                changes[name] = values
        return changes

    def _accept(self):
        if not self.fields['title'].text().strip() or not self.fields['language'].text().strip():
            self.error.setText('Enter a title and a language before saving.')
            return
        if self.save_handler is not None:
            self.save_handler(self.changes())
        else:
            self.accept()
