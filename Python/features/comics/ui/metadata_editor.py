"""Metadata dialog controller: loading, saving and protected navigation."""

from pathlib import Path
from commonUtils.ui import pyside as qt
from features.comics.selection import ComicSelection, normalize_targets
from .metadata_form import MetadataForm
from commonUtils.ui.operations import Operation
from services.zip_passwords import is_password_error
from ui_new.dialogs.archive_password import ask_password

WINDOW_SIZE = (789, 635)
BUTTON_SIZE = (105, 28)


class MetadataEditor(qt.QDialog):
    idle = qt.Signal()
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
        self.targets = normalize_targets(path)
        self.path = self.targets[0]
        self.siblings = list(siblings or [self.path])
        if self.path not in self.siblings:
            self.siblings.append(self.path)
        self.document = None
        self.selection = None
        self.busy = False
        self.pending_action = None
        self.last_save_error = None
        self.is_bulk = len(self.targets) > 1 or self.path.is_dir()
        self._setup_ui()
        self._load(self.targets)

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
        available = self.selection is not None and not self.busy
        self.tabs.setEnabled(available)
        self.ok_button.setEnabled(available)
        changes = self._changes()
        self.apply_button.setEnabled(available and bool(changes))
        if available and self.is_bulk and not self.last_save_error:
            fields = len(changes)
            count = len(self.selection.documents)
            self.message.setText(f'{count} comics · {fields} pending field(s). * = changed, ↶ = revert, × = clear mixed values.')
        self.cancel_button.setEnabled(not self.busy)
        index = self.siblings.index(self.path)
        self.previous_button.setEnabled(available and not self.is_bulk and index > 0)
        self.next_button.setEnabled(available and not self.is_bulk and index < len(self.siblings) - 1)

    def _operate(self, callback, finished):
        self.busy = True
        self._update_buttons()
        self.operation = Operation(callback, self)
        self.operation.completed.connect(finished)
        self.operation.finished.connect(self._finished)
        self.operation.finished.connect(self.idle)
        self.operation.start()

    def _finished(self):
        self.busy = False
        self.operation.deleteLater()
        self._update_buttons()
        action, self.pending_action = self.pending_action, None
        if action:
            action()

    def _load(self, targets, *, password=None):
        self.targets = normalize_targets(targets)
        self.path = self.targets[0]
        self.document = None
        self.selection = None
        self.last_save_error = None
        self.is_bulk = len(self.targets) > 1 or self.path.is_dir()
        title = f'{len(self.targets)} selected items' if self.is_bulk else self.path.name
        self.setWindowTitle(f'Edit Metadata — {title}')
        self.message.setVisible(self.is_bulk)
        self.message.setText('Reading selected comics…')
        self._operate(lambda: ComicSelection(self.targets, password=password), self._loaded)

    def _loaded(self, selection, error):
        if error:
            self.message.show()
            self.message.setText(f'Cannot read metadata: {error}')
            if not self.is_bulk and is_password_error(error):
                password = ask_password(self.path, error, self)
                if password is not None:
                    targets = self.targets
                    self.pending_action = lambda: self._load(targets, password=password)
            return
        try:
            self.tabs.load_values(selection.field_values(self.editors))
        except Exception as error:
            self.message.show()
            self.message.setText(f'Cannot read metadata: {error}')
            return
        self.selection = selection
        self.document = selection.documents[0]
        count = len(selection.documents)
        self.is_bulk = self.is_bulk or count > 1
        if self.is_bulk:
            # Batch status and field actions need extra room while preserving
            # the compact single-file proportions.
            self.resize(self.width(), max(self.height(), WINDOW_SIZE[1] + 48))
            self.setWindowTitle(f'Edit Metadata — {count} comics')
            self.message.show()
            self.message.setText(f'{count} comics. Muted fields have multiple values. Only fields marked * will change.')
            if selection.load_failures:
                details = '\n'.join(f'{path}: {message}' for path, message in selection.load_failures.items())
                self.message.setText(f'{count} editable comics; {len(selection.load_failures)} locked comics will be skipped. Only fields marked * will change.')
                qt.QMessageBox.warning(self, 'Locked comics were skipped', details)
        else:
            self.message.setText('Only changed fields are saved; other XML metadata is retained.' if self.document.exists else
                                 'No ComicInfo.xml yet. Apply or OK will create it when fields are changed.')

    def _save(self, after=None):
        if self.busy or self.selection is None:
            return
        changes = self._changes()
        if not changes:
            if after:
                after()
            return
        selection = self.selection
        self.last_save_error = None
        self.pending_action = after
        self.message.setText('Saving and verifying the comic archive…')
        def save():
            return selection.save(changes)
        self._operate(save, self._saved)

    def _saved(self, result, error):
        if error:
            self.pending_action = None
            self.message.show()
            self.last_save_error = f'Could not save: {error}. Close and reopen this editor to refresh changed files.'
            self.message.setText(self.last_save_error)
            qt.QMessageBox.warning(self, 'Metadata was not saved', error)
            return
        for path in result.saved:
            self.saved.emit(path)
        if result.failed:
            self.pending_action = None
            pending = self._changes()
            self.tabs.load_values(self.selection.field_values(self.editors))
            self.tabs.apply_pending(pending)
            details = '\n'.join(f'{path}: {message}' for path, message in result.failed.items())
            self.message.show()
            self.last_save_error = f'{len(result.saved)} saved; {len(result.failed)} failed. Pending changes are kept.'
            self.message.setText(self.last_save_error)
            qt.QMessageBox.warning(self, 'Some metadata was not saved', details)
        else:
            self.tabs.load_values(self.selection.field_values(self.editors))
            self.message.setText(f'Metadata saved to {len(result.saved)} comic(s).')

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
        if not self.busy:
            super().reject()

    def request_close(self):
        from commonUtils.ui.document_host import CloseOutcome, close_document, document_is_open
        if self.busy:
            return CloseOutcome.PENDING
        accepted = close_document(self)
        return CloseOutcome.ACCEPTED if accepted or not document_is_open(self) else CloseOutcome.VETOED

    def closeEvent(self, event):
        event.ignore()
        self.reject()
