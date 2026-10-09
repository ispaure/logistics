"""Logistics-owned standalone document window with native Qt document tabs."""

from commonUtils.ui import pyside as qt
from commonUtils.ui.operation_progress import OperationProgress
from commonUtils.ui.reader_menus import RecentFiles
from commonUtils.storage import cache_directory
from commonUtils.ui.code_editor.syntax import LANGUAGES
from .file_operations import FileOperations
from .editing import EditingCommands
from .syntax_settings import SyntaxSettings


class DocumentTabs(qt.QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabsClosable(True)
        self.setMovable(True)
        self.setDocumentMode(True)
        self.tabBar().installEventFilter(self)

    def eventFilter(self, watched, event):
        if (
            event.type() == qt.QEvent.Type.MouseButtonRelease
            and event.button() == qt.Qt.MouseButton.MiddleButton
        ):
            index = self.tabBar().tabAt(event.position().toPoint())
            if index >= 0:
                self.tabCloseRequested.emit(index)
            return True
        return super().eventFilter(watched, event)


class EditorWindow(SyntaxSettings, EditingCommands, FileOperations, qt.QMainWindow):
    idle = qt.Signal()
    saved = qt.Signal(object)

    def __init__(self, *, history_path=None, preferences_path=None):
        super().__init__()
        self.setWindowTitle("Text Editor — Logistics")
        self.resize(1100, 780)
        self.setMinimumSize(640, 420)
        self._initialize_preferences(preferences_path)
        self.tabs = DocumentTabs(self)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._active_changed)
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
        for widget in (self.external_notice, reload, keep):
            row.addWidget(widget)
        layout.addWidget(self.external_bar)
        self.external_bar.hide()
        layout.addWidget(self.tabs, 1)
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
        self.new_document()

    @property
    def current(self):
        return self.tabs.currentWidget()

    @property
    def documents(self):
        return [self.tabs.widget(index) for index in range(self.tabs.count())]

    def document_entries(self):
        """Expose individual buffers to the application's document switcher."""
        return [(self.tabs.tabText(index) if self.tabs.widget(index).path else f'Untitled {index+1}' +
                 (' *' if self.tabs.widget(index).modified else ''), self.tabs.widget(index))
                for index in range(self.tabs.count())]

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
                "Close Tab",
                lambda: self.close_tab(self.tabs.currentIndex()),
                qt.QKeySequence.StandardKey.Close,
            ),
            ("close_all", "Close All", self.close_all, None),
        ]:
            self.action(file, key, label, callback, shortcut)
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
        self.action(
            view, "next_tab", "Next Tab", lambda: self.change_tab(1), "Ctrl+Tab"
        )
        self._view_menu = view
        self.action(
            view,
            "previous_tab",
            "Previous Tab",
            lambda: self.change_tab(-1),
            "Ctrl+Shift+Tab",
        )

    def edit(self, method):
        if self.current:
            editor = self.current.editor
            if editor.isReadOnly() and method in ("undo", "redo", "cut", "paste"):
                return
            getattr(editor, method)()

    def change_tab(self, direction):
        if self.tabs.count():
            self.tabs.setCurrentIndex(
                (self.tabs.currentIndex() + direction) % self.tabs.count()
            )

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
        index = self.tabs.indexOf(document)
        if index >= 0:
            self.tabs.setTabText(
                index, document.title + (" [disk]" if document.external_changed else "")
            )
            self.tabs.setTabToolTip(
                index, str(document.path) if document.path else "Unsaved document"
            )
        if document is self.current:
            self._active_changed()

    def _active_changed(self, *args):
        if not hasattr(self, "position"):
            return
        document = self.current
        if hasattr(self, "search"):
            self.search.set_editor(document.editor if document else None)
        if document:
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
        else:
            self._close_pending = self.task.busy
            event.ignore()
