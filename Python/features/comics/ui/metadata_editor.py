"""Metadata dialog controller: loading, saving and protected navigation."""

from pathlib import Path
from commonUtils.ui import pyside as qt
from features.comics.library import ComicDocument
from .metadata_form import MetadataForm
from .operations import Operation

WINDOW_SIZE = (789, 635)
BUTTON_SIZE = (105, 28)


class MetadataEditor(qt.QDialog):
    saved = qt.Signal(object)

    def __init__(self, path, siblings=None, parent=None):
        super().__init__(parent)
        self.setWindowFlag(qt.Qt.WindowType.Window, True)
        # Reference images are 789 x 673/677, including a ~38px title bar.
        # Qt controls use logical pixels; the OS supplies its own title bar.
        self.resize(*WINDOW_SIZE)
        font = self.font()
        font.setPointSizeF(10)
        self.setFont(font)
        self.path = Path(path)
        self.siblings = list(siblings or [self.path])
        if self.path not in self.siblings:
            self.siblings.append(self.path)
        self.document = None
        self.busy = False
        self.pending_action = None
        self._setup_ui()
        self._load(self.path)

    def _setup_ui(self):
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(9, 10, 9, 9)
        layout.setSpacing(8)
        self.tabs = MetadataForm(self)
        self.editors = self.tabs.editors
        self.tabs.changed.connect(self._update_buttons)
        layout.addWidget(self.tabs, 1)
        self.message = qt.QLabel()
        self.message.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.message.setWordWrap(True)
        self.message.hide()
        layout.addWidget(self.message)
        buttons = qt.QHBoxLayout()
        buttons.setSpacing(10)
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
        self.apply_button.clicked.connect(lambda: self._save())
        for button in (self.ok_button, self.cancel_button, self.apply_button):
            buttons.addWidget(button)
        for button in (self.previous_button, self.next_button, self.ok_button,
                       self.cancel_button, self.apply_button):
            button.setFixedSize(*BUTTON_SIZE)
        layout.addLayout(buttons)

    def _changes(self):
        return self.tabs.changes()

    def _update_buttons(self):
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
            self.message.show()
            self.message.setText(f'Cannot read metadata: {error}')
            return
        try:
            self.tabs.load(document.info)
        except Exception as error:
            self.message.show()
            self.message.setText(f'Cannot read metadata: {error}')
            return
        self.document = document
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
            self.document.prepare_metadata(changes)
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
            self.tabs.mark_saved()
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
