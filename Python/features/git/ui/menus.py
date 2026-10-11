"""Publish existing Git commands through the shared workspace menu router."""
from commonUtils.ui import pyside as qt
from shiboken6 import isValid


class RepositoryMenus(qt.QObject):
    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.rules = []
        view.menuBar().setNativeMenuBar(False)
        self.menus = {name: view.menuBar().addMenu(name)
                      for name in ('File', 'Edit', 'View', 'Repository', 'Actions')}
        for menu in self.menus.values():
            menu.aboutToShow.connect(self.update)
        # Share the actual actions: toolbar badges, enabled state, and preference
        # changes remain authoritative in both presentations.
        for action in view.repository_menu.actions():
            self.menus['File'].addAction(action)
            self.rules.append((action, 'idle'))
        key = qt.QKeySequence.StandardKey
        self.shortcut(view.repository_menu.actions()[0], key.Open)
        self.edit_actions = {}
        for title, method, shortcut in (
            ('Undo', 'undo', key.Undo), ('Redo', 'redo', key.Redo),
            ('Cut', 'cut', key.Cut), ('Copy', 'copy', key.Copy),
            ('Paste', 'paste', key.Paste), ('Select All', 'selectAll', key.SelectAll),
        ):
            self.edit_actions[method] = self.add('Edit', title, lambda method=method: self.edit(method), shortcut=shortcut)
        self.add('Edit', 'Copy Selected Commit Hash', self.copy_hash, 'commit')
        self.add('Edit', 'Find in History…', lambda: self.show_view(2), 'ready', key.Find)
        for index, title in enumerate(('File Status', 'History', 'Search')):
            action = self.add('View', title, lambda index=index: self.show_view(index), 'ready', f'Ctrl+{index + 1}')
            action.setCheckable(True)
        self.menus['View'].addSeparator()
        self.log_action = self.add('View', 'Operation Log', view.log_toggle.toggle)
        self.log_action.setCheckable(True)
        view.log_toggle.toggled.connect(self.log_action.setChecked)
        self.log_action.setChecked(view.log_toggle.isChecked())
        for title in ('Refresh', 'Commit', 'Pull…', 'Push…', 'Fetch', 'Branch…', 'Merge…', 'Stash…', 'Settings'):
            action = view.action_buttons[title].defaultAction()
            self.menus['Repository'].addAction(action)
            if title == 'Refresh': self.shortcut(action, key.Refresh)
        self.menus['Repository'].addSeparator()
        for action in view.more_menu.actions():
            title = action.text()
            destination = 'Actions' if title.startswith(('Cherry-pick', 'Revert', 'Compare', 'External')) or action.menu() is view.custom_menu else 'Repository'
            self.menus[destination].addAction(action)
            rule = 'commit' if title.startswith(('Cherry-pick', 'Revert', 'Compare')) else 'file' if title.startswith('External diff') else 'conflict' if title.startswith('External merge') else 'idle' if title == 'Git preferences…' else 'ready'
            self.rules.append((action, rule))
        self.menus['Actions'].addSeparator()
        for title in ('View Remote', 'Show in Finder', 'Open Folder', 'Terminal'):
            if title in view.action_buttons:
                self.menus['Actions'].addAction(view.action_buttons[title].defaultAction())
        self.menus['Actions'].addSeparator()
        for title, callback, rule in (
            ('Stage Selected Files', view.changes.stage_selected, 'unstaged'),
            ('Unstage Selected Files', view.changes.unstage_selected, 'staged'),
            ('Stage All Files', view.changes.stage_all, 'unstaged_all'),
            ('Unstage All Files', view.changes.unstage_all, 'staged_all'),
            ('Discard Selected File Edits…', view.changes.discard_selected, 'unstaged'),
            ('Open Selected Working File', lambda: self.selected_file(False), 'file'),
            ('Resolve Selected Conflict…', lambda: self.selected_file(True), 'conflict'),
            ('Continue Operation', view.finish_operation, 'operation'),
            ('Abort Operation…', lambda: view.finish_operation(True), 'operation'),
            ('Cancel Operation', view.cancel, 'busy'),
        ):
            self.add('Actions', title, callback, rule)
        for tree in (view.changes.staged_files, view.changes.unstaged_files, view.history.table):
            tree.itemSelectionChanged.connect(self.update)
        for widget in view.findChildren(qt.QWidget):
            if isinstance(widget, (qt.QLineEdit, qt.QTextEdit, qt.QPlainTextEdit)):
                widget.textChanged.connect(lambda *args: self.update())
                widget.selectionChanged.connect(self.update)
        view.views.currentChanged.connect(lambda index: self.update())
        qt.QApplication.instance().focusChanged.connect(self.focus_changed)
        self.update()

    def add(self, menu, title, callback, rule=None, shortcut=None):
        action = self.menus[menu].addAction(title)
        action.setMenuRole(qt.QAction.MenuRole.NoRole)
        action.triggered.connect(lambda checked=False: callback())
        if rule: self.rules.append((action, rule))
        if shortcut is not None: self.shortcut(action, shortcut)
        return action

    def shortcut(self, action, shortcut):
        action.setShortcut(qt.QKeySequence(shortcut))
        action.setShortcutContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.view.addAction(action)

    def focus_changed(self, old, current):
        self.update()

    def editor(self):
        widget = qt.QApplication.focusWidget()
        if widget is not None and self.view.isAncestorOf(widget) and widget.isEnabled():
            if isinstance(widget, (qt.QLineEdit, qt.QTextEdit, qt.QPlainTextEdit)):
                return widget
        return None

    def edit(self, method):
        editor = self.editor()
        if editor is not None: getattr(editor, method)()

    def show_view(self, index):
        self.view.views.setCurrentIndex(index)
        if index == 2: self.view.search_results.search.setFocus()

    def copy_hash(self):
        commit = self.view.history.selected_commit()
        if commit: qt.QApplication.clipboard().setText(commit.oid)

    def selected_file(self, resolve):
        changes = self.view.changes.selected()
        if len(changes) == 1:
            (self.view.resolve_conflict if resolve else self.view.edit_file)(changes[0].path)

    def update(self, busy=None):
        view = self.view
        if not isValid(view) or view.closing or not isValid(view.changes):
            return
        busy = view.busy if busy is None else busy
        ready = view.snapshot is not None and not busy and not view.closing
        files = view.changes.selected() if view.views.currentIndex() == 0 else []
        commit = view.history.selected_commit() if view.views.currentIndex() == 1 else None
        states = {
            'idle': not busy and not view.closing, 'ready': ready, 'busy': busy,
            'commit': ready and commit is not None,
            'file': ready and len(files) == 1,
            'conflict': ready and len(files) == 1 and files[0].conflict,
            'staged': ready and bool(files) and bool(view.changes.selected(True)),
            'unstaged': ready and bool(files) and bool(view.changes.selected(False)),
            'staged_all': ready and any(c.staged for c in view.changes.changes),
            'unstaged_all': ready and any(c.unstaged for c in view.changes.changes),
            'operation': ready and view.snapshot.operation in ('merge', 'rebase', 'cherry-pick', 'revert'),
        }
        for action, rule in self.rules:
            if isValid(action): action.setEnabled(states[rule])
        for index, action in enumerate(self.menus['View'].actions()[:3]):
            action.setChecked(view.views.currentIndex() == index)
        editor = self.editor()
        writable = editor is not None and not editor.isReadOnly()
        selection = editor.hasSelectedText() if isinstance(editor, qt.QLineEdit) else editor.textCursor().hasSelection() if editor else False
        for method, action in self.edit_actions.items():
            enabled = editor is not None
            if method in ('cut', 'paste', 'undo', 'redo'): enabled = writable
            if method in ('cut', 'copy'): enabled = enabled and selection
            if method in ('undo', 'redo') and editor is not None:
                source = editor if isinstance(editor, qt.QLineEdit) else editor.document()
                enabled = enabled and getattr(source, 'isUndoAvailable' if method == 'undo' else 'isRedoAvailable')()
            action.setEnabled(enabled)
