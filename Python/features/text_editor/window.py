"""One text document per host tab or standalone editor window."""

from commonUtils.ui import pyside as qt
from commonUtils.ui.document_host import close_document
from commonUtils.ui.operation_progress import OperationProgress
from commonUtils.ui.reader_menus import RecentFiles
from commonUtils.storage import cache_directory
from commonUtils.ui.code_editor.syntax import LANGUAGES
from .file_operations import FileOperations
from .editing import EditingCommands
from .syntax_settings import SyntaxSettings
from .commands import CommandControls


class EditorWindow(CommandControls, SyntaxSettings, EditingCommands, FileOperations, qt.QMainWindow):
    document_editor_name = 'Text Editor'
    document_editor_id = 'text'
    idle = qt.Signal()
    saved = qt.Signal(object)
    closed = qt.Signal()

    def __init__(self, *, history_path=None, preferences_path=None, service=None, create_blank=True):
        super().__init__()
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("Text Editor — Logistics")
        self.resize(1100, 780)
        self.setMinimumSize(640, 420)
        self._initialize_preferences(preferences_path)
        self.document_stack = qt.QStackedWidget(self)
        self.document_stack.currentChanged.connect(self._active_changed)
        self._opening_path = None
        from .service import EditorService
        self.service = service or EditorService(qt.QApplication.instance(),
            history_path=history_path, preferences_path=preferences_path)
        self.service.register(self)
        self._queue = []
        self._close_pending = False
        self._done = None
        self._failed = None
        self.recent = RecentFiles(
            path=history_path
            or cache_directory(create=False) / "TextEditor" / "recent.json"
        )
        central = qt.QWidget()
        layout = qt.QVBoxLayout(central)
        layout.setContentsMargins(8, 4, 8, 4)
        self.external_bar = qt.QWidget()
        row = qt.QHBoxLayout(self.external_bar)
        self.external_notice = qt.QLabel()
        self.external_notice.setWordWrap(True)
        reload = qt.QPushButton("Reload")
        reload.clicked.connect(self.reload_document)
        keep = qt.QPushButton("Keep Buffer")
        keep.clicked.connect(self._keep_buffer)
        compare = qt.QPushButton("Compare")
        compare.clicked.connect(self.compare_disk)
        merge = qt.QPushButton("Merge…")
        merge.clicked.connect(self.merge_disk)
        for widget in (self.external_notice, compare, merge, reload, keep):
            row.addWidget(widget)
        layout.addWidget(self.external_bar)
        self.external_bar.hide()
        layout.addWidget(self.document_stack, 1)
        self.task = OperationProgress(self)
        self.task.completed.connect(self._finished)
        layout.addWidget(self.task)
        self.setCentralWidget(central)
        self.watcher = qt.QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._external_change)
        self.actions = {}
        self._build_menus()
        self._build_status()
        self._build_editing(layout)
        self._build_syntax_controls()
        self._build_command_controls()
        if create_blank:
            from .document import Document
            self._add_document(Document())

    @property
    def current(self):
        return self.document_stack.currentWidget()

    @property
    def documents(self):
        return [self.document_stack.widget(index) for index in range(self.document_stack.count())]

    def document_entries(self):
        """The host owns tab navigation; this editor has one document."""
        return [(self.current.title if self.current else self.windowTitle(), None)]

    def show_error(self, error):
        qt.QMessageBox.warning(self, "Text Editor", str(error))

    def action(self, menu, key, label, callback, shortcut=None, *, checkable=False):
        action = menu.addAction(label)
        action.setCheckable(checkable)
        if shortcut is not None:
            action.setShortcut(qt.QKeySequence(shortcut))
        action.setShortcutContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.addAction(action)
        action.triggered.connect(lambda checked=False: callback())
        self.actions[key] = action
        return action

    def _build_menus(self):
        file = self.menuBar().addMenu("&File")
        for key, label, callback, shortcut in [
            ("new", "New", self.new_document, qt.QKeySequence.StandardKey.New),
            ("open", "Open…", self.open_dialog, qt.QKeySequence.StandardKey.Open),
            ("force", "Force Open as Text…", lambda: self.open_dialog(True), None),
            ("save", "Save", self.save_document, qt.QKeySequence.StandardKey.Save),
            (
                "save_as",
                "Save As…",
                lambda: self.save_document(save_as=True),
                qt.QKeySequence.StandardKey.SaveAs,
            ),
            ("save_all", "Save All", self.save_all, "Ctrl+Alt+S"),
            ("reload", "Reload from Disk", self.reload_document, None),
            (
                "close",
                "Close Document",
                lambda: close_document(self),
                qt.QKeySequence.StandardKey.Close,
            ),
            ("close_all", "Close All", self.close_all, None),
        ]:
            self.action(file, key, label, callback, shortcut)
        self.action(file, "restore_session", "Restore Editor Session…", lambda: self.service.session.restore_selected(self))
        self.action(file, "suspend_session", "Keep Session and Close Editors", self.service.suspend)
        self.recent_menu = file.addMenu("Open Recent")
        self.recent_menu.aboutToShow.connect(self._recent_menu)
        edit = self.menuBar().addMenu("&Edit")
        self._edit_menu = edit
        for method, shortcut in [
            ("undo", qt.QKeySequence.StandardKey.Undo),
            ("redo", qt.QKeySequence.StandardKey.Redo),
            ("cut", qt.QKeySequence.StandardKey.Cut),
            ("copy", qt.QKeySequence.StandardKey.Copy),
            ("paste", qt.QKeySequence.StandardKey.Paste),
            ("selectAll", qt.QKeySequence.StandardKey.SelectAll),
        ]:
            self.action(
                edit,
                method,
                {"selectAll": "Select All"}.get(method, method.title()),
                lambda method=method: self.edit(method),
                shortcut,
            )
        view = self.menuBar().addMenu("&View")
        self._view_menu = view

    def edit(self, method):
        if self.current:
            editor = self.current.editor
            if editor.isReadOnly() and method in ("undo", "redo", "cut", "paste"):
                return
            getattr(editor, method)()

    def _recent_menu(self):
        self.recent_menu.clear()
        for path in self.recent.paths()[:12]:
            action = self.recent_menu.addAction(path.name.replace("&", "&&"))
            action.setToolTip(str(path))
            action.triggered.connect(
                lambda checked=False, path=path: self.open_path(path)
            )
        if not self.recent_menu.actions():
            self.recent_menu.addAction("No recent files").setEnabled(False)

    def _build_status(self):
        self.position = qt.QLabel()
        self.statusBar().addWidget(self.position, 1)

    def _document_changed(self, document):
        if document is self.current:
            self._active_changed()

    def _active_changed(self, *args):
        if not hasattr(self, "position"):
            return
        document = self.current
        if hasattr(self, "search"):
            self.search.set_editor(document.editor if document else None)
        if document:
            if document.editor.hasFocus():
                self.service.window = self
            cursor = document.editor.textCursor()
            self.position.setText(
                f"Ln {cursor.blockNumber() + 1}, Col {cursor.positionInBlock() + 1} · {document.editor.blockCount()} lines · {document.encoding.upper()}"
            )
            if hasattr(self, "encoding_button"):
                self._editing_status(document)
            if hasattr(self, "language_button"):
                self.language_button.setText(
                    dict((alias, name) for name, alias in LANGUAGES).get(
                        document.language, document.language
                    )
                )
            if "indent_guides" in self.actions:
                self.actions["indent_guides"].setChecked(document.editor.indent_guides)
            if "comment" in self.actions:
                self.actions["comment"].setEnabled(
                    document.editor.comment_prefix is not None
                )
            self.setWindowTitle(f"{document.title} — Text Editor — Logistics")
            if document.external_changed and not document.external_acknowledged:
                self.external_bar.show()
            else:
                self.external_bar.hide()
        else:
            self.position.clear()
        self._update_actions()

    def _update_actions(self):
        if not hasattr(self, "actions"):
            return
        for key in ("save", "save_as", "save_all", "reload", "close", "close_all"):
            if key in self.actions:
                self.actions[key].setEnabled(
                    self.current is not None and not self.task.busy
                )

    def _keep_buffer(self):
        if self.current:
            self.current.external_acknowledged = True
        self.external_bar.hide()

    def request_close(self):
        from commonUtils.ui.document_host import CloseOutcome, close_document
        accepted = close_document(self)
        if accepted:
            return CloseOutcome.ACCEPTED
        return CloseOutcome.PENDING if self._close_pending else CloseOutcome.VETOED

    def closeEvent(self, event):
        if self.task.busy or self._queue or not self.search.prepare_close():
            self._close_pending = True
            event.ignore()
            return
        if self.prepare_close():
            self.options["geometry_str"] = (
                self.saveGeometry().toHex().data().decode("ascii")
            )
            self._preference_timer.stop()
            self._save_preferences()
            event.accept()
            self.closed.emit()
        else:
            self._close_pending = self.task.busy
            event.ignore()
