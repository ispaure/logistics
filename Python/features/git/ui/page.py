"""Git workspace orchestration. Domain commands stay in repository.py.

One retained worker owns each operation; switching repositories, mutating actions,
and refreshes cannot overlap. Failures remain visible and trigger a fresh snapshot
after writes, including conflicts and cancelled network operations.
"""
from pathlib import Path
import sys

from commonUtils.ui import pyside as qt
from ..preferences import Preferences
from ..repository import Repository, clone, initialize
from ..runner import CommandResult, redact
from .changes import ChangesPanel
from .dialogs import FormDialog
from .history import HistoryPanel
from .preview import Preview
from .worker import GitWorker
from .repository_tools import RepositoryTools
from .chrome import toolbar_button, WORKSPACE_STYLE


class GitPage(qt.QWidget):
    idle = qt.Signal()

    def __init__(self, parent=None, *, preferences_path=None):
        super().__init__(parent)
        self.setProperty('navigation_position', 'workspace')
        self.setProperty('navigation_order', 20)
        self.preferences = Preferences(preferences_path)
        self.worker = None
        self.snapshot = None
        self.path = None
        self.history_limit = 200
        self.closing = False
        self._refresh_pending = False
        self.repository_tools = RepositoryTools(self)
        self._build()
        self._repositories()
        self._set_busy(False)
        if self.preferences.warning: self._message(self.preferences.warning, error=True)
        if self.preferences.last_repository:
            qt.QTimer.singleShot(0, self, lambda: self.open_repository(self.preferences.last_repository))

    def _build(self):
        layout = qt.QVBoxLayout(self)
        self.setObjectName('gitWorkspace')
        self.setStyleSheet(WORKSPACE_STYLE)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        toolbar_font = qt.QFont(self.font())
        content_font = qt.QFont(toolbar_font)
        content_font.setPointSizeF(max(8.0, toolbar_font.pointSizeF() - 1.0))
        self.setFont(content_font)
        self.repositories = qt.QComboBox(self)
        self.repositories.hide()
        self.repositories.currentIndexChanged.connect(self._repository_selected)
        self.repository_menu = qt.QToolButton()
        self.repository_menu.setText('+ Repositories')
        self.repository_menu.setAccessibleName('Open, clone or manage repositories')
        self.repository_menu.setPopupMode(qt.QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = qt.QMenu(self.repository_menu)
        for title, callback in (('Open…',self.open_dialog),('Clone…',self.clone_dialog),
                               ('Init…',self.init_dialog),('Manage bookmarks…',self.manage_repositories)):
            menu.addAction(title,callback)
        self.repository_menu.setMenu(menu)
        self.global_buttons = [self.repository_menu]
        self.repository_label = qt.QLabel()
        self.repository_label.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.repository_label.hide()
        self.toolbar = qt.QWidget()
        self.toolbar.setObjectName('gitToolbar')
        self.toolbar.setFont(toolbar_font)
        actions = qt.QHBoxLayout(self.toolbar)
        actions.setContentsMargins(8, 6, 8, 6)
        actions.setSpacing(2)
        self.action_buttons = {}
        for title, icon, callback in (
                ('Commit', 'commit', self.focus_commit), ('Pull…', 'pull', self.pull_dialog),
                ('Push…', 'push', self.push_dialog), ('Fetch', 'fetch', self.fetch),
                ('Branch…', 'branch', self.branch_dialog), ('Merge…', 'merge', self.merge_dialog),
                ('Stash…', 'stash', self.stash_dialog)):
            button = toolbar_button(title, icon, callback, self.toolbar)
            actions.addWidget(button)
            self.action_buttons[title] = button
        actions.addStretch()
        for title, icon, callback in (
                ('View Remote', 'remote', self.view_remote), ('Show in Finder' if sys.platform == 'darwin' else 'Open Folder', 'folder', self.open_folder),
                ('Terminal', 'terminal', self.open_terminal), ('Refresh', 'fetch', self.refresh),
                ('Settings', 'settings', self.settings_dialog), ('More…', 'more', self.show_more)):
            button = toolbar_button(title, icon, callback, self.toolbar)
            actions.addWidget(button)
            self.action_buttons[title] = button
        layout.insertWidget(0, self.toolbar)
        self.repository_tabs = qt.QTabBar()
        self.repository_tabs.setExpanding(False)
        self.repository_tabs.setAccessibleName('Open repository bookmarks')
        self.repository_tabs.currentChanged.connect(self._repository_tab_selected)
        tabs_row = qt.QHBoxLayout()
        tabs_row.setContentsMargins(0,0,6,0)
        tabs_row.addWidget(self.repository_tabs,1)
        tabs_row.addWidget(self.repository_menu)
        layout.addLayout(tabs_row)
        self.operation_bar = qt.QWidget()
        operation_layout = qt.QHBoxLayout(self.operation_bar)
        operation_layout.setContentsMargins(0, 0, 0, 0)
        self.operation_label = qt.QLabel()
        operation_layout.addWidget(self.operation_label, 1)
        for title, abort in (('Continue', False), ('Abort…', True)):
            button = qt.QPushButton(title)
            button.clicked.connect(lambda checked=False, abort=abort: self.finish_operation(abort))
            operation_layout.addWidget(button)
        self.operation_bar.hide()
        layout.addWidget(self.operation_bar)
        self.content = qt.QSplitter(qt.Qt.Orientation.Horizontal)
        sidebar = qt.QWidget()
        sidebar.setObjectName('gitSidebar')
        sidebar_layout = qt.QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(4, 4, 4, 4)
        sidebar_layout.setSpacing(4)
        self.refs = qt.QTreeWidget()
        self.refs.setHeaderHidden(True)
        self.refs.setMinimumWidth(170)
        self.refs.setIconSize(qt.QSize(14,14))
        self.refs.setIndentation(14)
        self.refs.setUniformRowHeights(False)
        self.refs.setAccessibleName('Git workspace navigation and references')
        self.refs.itemClicked.connect(self._navigation_selected)
        self.refs.itemDoubleClicked.connect(self._ref_activated)
        self.refs.setContextMenuPolicy(qt.Qt.ContextMenuPolicy.CustomContextMenu)
        self.refs.customContextMenuRequested.connect(self.ref_menu)
        sidebar_layout.addWidget(self.refs, 1)
        self.ref_filter = qt.QLineEdit()
        self.ref_filter.setPlaceholderText('Filter references')
        self.ref_filter.textChanged.connect(self._filter_refs)
        sidebar_layout.addWidget(self.ref_filter)
        self.content.addWidget(sidebar)
        self.views = qt.QTabWidget()
        self.views.tabBar().hide()
        self.changes = ChangesPanel()
        self.history = HistoryPanel()
        self.preview = Preview()
        code_font = qt.QFont(self.preview.editor.font())
        code_font.setPointSizeF(max(8.0, code_font.pointSizeF() - 1.0))
        self.preview.editor.setFont(code_font)
        self.change_split = qt.QSplitter(qt.Qt.Orientation.Horizontal)
        self.change_split.addWidget(self.changes)
        self.change_preview_host = qt.QWidget()
        self.change_preview_layout = qt.QVBoxLayout(self.change_preview_host)
        self.change_preview_layout.setContentsMargins(0, 0, 0, 0)
        self.change_preview_layout.addWidget(self.preview)
        self.change_split.addWidget(self.change_preview_host)
        self.change_split.setSizes([350, 650])
        change_view = qt.QWidget()
        change_layout = qt.QVBoxLayout(change_view)
        change_layout.setContentsMargins(0, 0, 0, 0)
        change_layout.setSpacing(0)
        change_layout.addWidget(self.change_split, 1)
        change_layout.addWidget(self.changes.composer)
        self.views.addTab(change_view, 'File status')
        history_view = qt.QSplitter(qt.Qt.Orientation.Vertical)
        history_view.addWidget(self.history)
        self.history_bottom = qt.QSplitter(qt.Qt.Orientation.Horizontal)
        self.history_bottom.addWidget(self.history.details)
        self.history_preview_host = qt.QWidget()
        self.history_preview_layout = qt.QVBoxLayout(self.history_preview_host)
        self.history_preview_layout.setContentsMargins(0, 0, 0, 0)
        self.history_bottom.addWidget(self.history_preview_host)
        self.history_bottom.setSizes([450, 550])
        history_view.addWidget(self.history_bottom)
        history_view.setSizes([440, 300])
        self.views.addTab(history_view, 'History')
        self.content.addWidget(self.views)
        self.content.setSizes([210, 1040])
        self.content.setStretchFactor(0, 0)
        self.content.setStretchFactor(1, 1)
        layout.addWidget(self.content, 1)
        self.changes.change_selected.connect(self.preview_change)
        self.changes.stage_requested.connect(lambda paths: self._operation('Stage files', lambda repo: repo.stage(paths)))
        self.changes.unstage_requested.connect(lambda paths: self._operation('Unstage files', lambda repo: repo.unstage(paths)))
        self.changes.discard_requested.connect(self.discard_dialog)
        self.changes.commit_requested.connect(self.commit)
        self.changes.edit_requested.connect(self.edit_file)
        self.history.commit_selected.connect(self.preview_commit)
        self.history.blob_selected.connect(self.preview_blob)
        self.history.load_more.connect(self.load_more)
        self.views.currentChanged.connect(self._view_changed)
        self.preview.stage_button.clicked.connect(self.changes.stage_selected)
        self.preview.unstage_button.clicked.connect(self.changes.unstage_selected)
        self.preview.discard_button.clicked.connect(self.changes.discard_selected)
        status = qt.QHBoxLayout()
        self.status = qt.QLabel('Ready')
        self.status.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        status.addWidget(self.status, 1)
        self.progress = qt.QProgressBar()
        self.progress.setMaximumWidth(140)
        self.progress.setRange(0, 0)
        self.progress.hide()
        status.addWidget(self.progress)
        self.cancel_button = qt.QPushButton('Cancel operation')
        self.cancel_button.clicked.connect(self.cancel)
        status.addWidget(self.cancel_button)
        self.log_toggle = qt.QToolButton()
        self.log_toggle.setText('Operation log')
        self.log_toggle.setCheckable(True)
        status.addWidget(self.log_toggle)
        layout.addLayout(status)
        self.log = qt.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(qt.QPlainTextEdit.LineWrapMode.NoWrap)
        self.log.setAccessibleName('Git operation log')
        self.log.setMaximumBlockCount(1500)
        self.log.setMaximumHeight(170)
        self.log.hide()
        self.log_toggle.toggled.connect(self.log.setVisible)
        layout.addWidget(self.log)
        self.more_menu = qt.QMenu(self)
        for title, callback in (('Merge branch…', self.merge_dialog), ('Cherry-pick selected commit…', self.cherry_pick),
                                ('Revert selected commit…', self.revert), ('Compare selected commit to HEAD', self.compare_to_head),
                                ('Create tag…', self.tag_dialog), ('Recover from reflog…', self.reflog_dialog),
                                ('Commit identity…', self.identity_dialog),
                                ('Add remote…', self.remote_dialog),
                                ('Worktrees…', self.repository_tools.worktrees_dialog), ('Submodules…', self.repository_tools.submodules_dialog),
                                ('Subtrees…', self.repository_tools.subtree_dialog), ('Open repository folder', self.open_folder)):
            self.more_menu.addAction(title, callback)
        # Widgets assembled without a parent can retain the application font when
        # reparented into splitters. Apply content sizing after the layout is built.
        for widget in self.findChildren(qt.QWidget):
            if widget is self.toolbar or self.toolbar.isAncestorOf(widget): continue
            if widget is self.preview.editor or self.preview.editor.isAncestorOf(widget): continue
            widget.setFont(content_font)

    @property
    def busy(self): return self.worker is not None

    def _set_busy(self, busy):
        available = self.snapshot is not None
        self.repositories.setEnabled(not busy)
        self.repository_tabs.setEnabled(not busy)
        for button in self.global_buttons: button.setEnabled(not busy)
        self.toolbar.setEnabled(not busy)
        for title, button in self.action_buttons.items(): button.setEnabled(not busy and (available or title == 'Settings'))
        self.content.setEnabled(available and not busy)
        self.operation_bar.setEnabled(available and not busy)
        self.cancel_button.setEnabled(busy)
        self.progress.setVisible(busy)

    def _message(self, text, error=False):
        self.status.setText(redact(text))
        self.status.setStyleSheet('color: #c55b62;' if error else '')

    def _append_log(self, text):
        cursor = self.log.textCursor()
        cursor.movePosition(qt.QTextCursor.MoveOperation.End)
        text = redact(text[-65536:]).replace('\r\n', '\n').replace('\r', '\n')
        # Hooks can emit arbitrarily long lines. Cap them before Qt shapes text;
        # retaining a megabyte-long single line can stall the GUI even without wrap.
        text = '\n'.join(line if len(line) <= 4000 else line[:4000] + '\n[Log line truncated]\n'
                         for line in text.split('\n'))
        cursor.insertText(text)
        count = self.log.document().characterCount()
        if count > 1024 * 1024:
            trim = qt.QTextCursor(self.log.document())
            trim.setPosition(0)
            trim.setPosition(count - 1024 * 1024, qt.QTextCursor.MoveMode.KeepAnchor)
            trim.removeSelectedText()
        self.log.setTextCursor(cursor)

    def _job(self, label, action, after=None, *, refresh=False):
        if self.busy or self.closing: return False
        self._message(label + '…')
        self._append_log('\n' + label + '\n')
        self._set_busy(True)
        worker = GitWorker(self.preferences.executable, action, self)
        self.worker = worker
        worker.progress.connect(self._append_log)
        worker.finished.connect(lambda: self._finished(worker, label, after, refresh))
        worker.start()
        return True

    def _finished(self, worker, label, after, refresh):
        self.worker = None
        self._set_busy(False)
        error = worker.error
        result = worker.result
        worker.deleteLater()
        if self.closing:
            self.idle.emit()
            return
        if error:
            self._message(error, error=not worker.cancelled)
            self._append_log(error + '\n')
            self.log_toggle.setChecked(True)
        else:
            self._message(label + ' completed.')
            if isinstance(result, CommandResult) and result.stdout:
                self._append_log(result.stdout[-65536:].decode('utf-8', 'replace') + '\n')
            if after:
                try: after(result)
                except (OSError, ValueError) as exc: self._message(str(exc), error=True)
        if (refresh or self._refresh_pending) and self.path and not self.busy:
            # Refresh even after failure: merge conflicts and cancellation can
            # leave valid new repository state. Keep the operation error visible.
            self._refresh_pending = False
            self._refresh(error)
        if not self.busy:
            if getattr(self, '_focus_search_pending', False):
                self._focus_search_pending = False
                self.history.search.setFocus()
            self.idle.emit()

    def _operation(self, label, action, after=None):
        if self.path is None: return
        path = self.path
        return self._job(label, lambda runner: action(Repository(path, runner)), after, refresh=True)

    def cancel(self):
        if self.worker:
            self.worker.cancel()
            self._message('Cancellation requested…')

    def prepare_close(self):
        self.closing = True
        if self.worker:
            self.cancel()
            return False
        return True

    def can_close(self):
        return self._discard_draft()

    def _discard_draft(self):
        if not self.changes.message.toPlainText().strip(): return True
        if not self._confirm('Discard commit message?', 'The uncommitted message draft will be discarded. Files and staged changes are kept.'):
            return False
        self.changes.message.clear()
        return True

    def _confirm(self, title, text):
        box = qt.QMessageBox(qt.QMessageBox.Icon.Question, title, text,
                             qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.No, self)
        box.setTextFormat(qt.Qt.TextFormat.PlainText)
        box.setDefaultButton(qt.QMessageBox.StandardButton.No)
        return box.exec() == qt.QMessageBox.StandardButton.Yes

    def _save(self):
        try: self.preferences.save()
        except OSError as exc:
            self._append_log(f'Settings were not saved: {exc}\n')
            self._message(f'Settings were not saved: {exc}', error=True)

    def _repositories(self):
        with qt.QSignalBlocker(self.repositories):
            self.repositories.clear()
            self.repositories.addItem('Choose a repository…', '')
            for entry in sorted(self.preferences.repositories, key=lambda e: not e['pinned']):
                path = Path(entry['path'])
                self.repositories.addItem(('★ ' if entry['pinned'] else '') + f'{path.name} — {path}', str(path))
            if self.path:
                index = self.repositories.findData(str(self.path))
                if index >= 0: self.repositories.setCurrentIndex(index)
        with qt.QSignalBlocker(self.repository_tabs):
            while self.repository_tabs.count(): self.repository_tabs.removeTab(0)
            for entry in self.preferences.repositories:
                path = Path(entry['path'])
                index = self.repository_tabs.addTab(path.name + ' (Git)')
                self.repository_tabs.setTabData(index, str(path))
                self.repository_tabs.setTabToolTip(index, str(path))
                if self.path == path: self.repository_tabs.setCurrentIndex(index)


    def _repository_tab_selected(self, index):
        path = self.repository_tabs.tabData(index)
        if path and str(self.path) != path: self.open_repository(path)

    def _repository_selected(self, index):
        path = self.repositories.itemData(index)
        if path: self.open_repository(path)

    def open_repository(self, path):
        if self.busy or self.closing: return
        path = Path(path).expanduser()
        if self.path and path.resolve() != self.path.resolve() and not self._discard_draft():
            self._repositories()
            return
        different = self.path is None or path.resolve() != self.path.resolve()
        limit = 200 if different else self.history_limit
        def opened(snapshot):
            self.history_limit = limit
            if different:
                self.history.tree.clear()
                self.preview.show_text('Select a changed file or commit', '')
                self.changes.amend.setChecked(False)
            self.path = snapshot.root
            self.preferences.remember(self.path)
            self._save()
            self._repositories()
            self._render(snapshot)
        self._job('Open repository', lambda runner: Repository(path, runner).snapshot(limit), opened)

    def refresh(self):
        if self.closing or not self.path: return
        if self.busy:
            self._refresh_pending = True
        else:
            self._refresh()

    def _refresh(self, operation_error=''):
        path, limit = self.path, self.history_limit
        def render(snapshot):
            self._render(snapshot)
            if operation_error: self._message(operation_error, error=True)
        self._job('Refresh repository', lambda runner: Repository(path, runner).snapshot(limit), render)

    def _render(self, snapshot):
        self.snapshot = snapshot
        self.path = snapshot.root
        status = snapshot.status
        branch = status.branch if status.branch != '(detached)' else f'Detached HEAD {status.oid[:8]}'
        tracking = f' · {status.upstream} · ↑{status.ahead} ↓{status.behind}' if status.upstream else ' · no upstream'
        self.repository_label.setText(f'  {snapshot.root.name} · {branch}{tracking}')
        self.repository_label.setToolTip(str(snapshot.root))
        self.changes.set_changes(status.changes)
        self.history.head_oid = status.oid
        self.history.set_commits(snapshot.commits, snapshot.more_history and self.history_limit < 5000)
        self._render_navigation(snapshot)
        self.operation_label.setText(f'{snapshot.operation} in progress — resolve conflicts, stage files, then Continue.')
        self.operation_bar.setVisible(snapshot.operation in ('merge', 'rebase', 'cherry-pick', 'revert'))
        self.changes.amend.setEnabled(bool(snapshot.commits) and not snapshot.operation)
        if snapshot.operation: self.changes.amend.setChecked(False)
        self._set_busy(self.busy)

    def _render_navigation(self, snapshot):
        from .navigation import populate_navigation
        populate_navigation(self, snapshot)
        self._select_navigation(self.views.currentIndex())
        self._filter_refs(self.ref_filter.text())

    def _select_navigation(self, index):
        if hasattr(self, 'workspace_items'):
            with qt.QSignalBlocker(self.refs): self.refs.setCurrentItem(self.workspace_items[index])

    def _navigation_selected(self, item, column):
        value = item.data(0, qt.Qt.ItemDataRole.UserRole)
        if not value: return
        kind, name, ref = value
        if kind == 'view':
            if name == 2: self._focus_search_pending = True
            self.views.setCurrentIndex(0 if name == 0 else 1)
            if name == 2:
                if not self.busy:
                    self._focus_search_pending = False
                    self.history.search.setFocus()
                self.refs.setCurrentItem(item)
        elif kind in ('branch', 'remote_branch', 'tag'):
            self.show_ref_commit(ref)

    def _filter_refs(self, text):
        def visit(item):
            visible = text.casefold() in item.text(0).casefold()
            for i in range(item.childCount()): visible = visit(item.child(i)) or visible
            item.setHidden(not visible)
            return visible
        for i in range(self.refs.topLevelItemCount()): visit(self.refs.topLevelItem(i))

    def focus_commit(self):
        self.views.setCurrentIndex(0)
        self.changes.message.setFocus()

    def view_remote(self):
        if not self.path or not self.snapshot.remotes: return
        from .chrome import browser_remote_url
        def show(address):
            url = browser_remote_url(address)
            if url: qt.QDesktopServices.openUrl(qt.QUrl(url))
            else: self._message('This remote has no HTTP browser address. Use Git settings or the operation log to inspect it.')
        self._job('Read remote address', lambda runner: Repository(self.path, runner).remote_details(self.snapshot.remotes[0]), show)

    def open_terminal(self):
        if not self.path: return
        from commonUtils.wrappers.cmdShellWrapper.terminal import exec_cmd_new_window
        try:
            if exec_cmd_new_window('', str(self.path)) is False: self._message('Terminal could not be opened.', error=True)
        except OSError as error: self._message(str(error), error=True)

    def open_dialog(self):
        path = qt.QFileDialog.getExistingDirectory(self, 'Open Git repository')
        if path: self.open_repository(path)

    def clone_dialog(self):
        if not self._discard_draft(): return
        dialog = FormDialog('Clone repository', self, 'SSH agents and Git credential helpers are used. Set up credentials outside Logistics before cloning private repositories.')
        url = dialog.text('Repository URL or local path')
        destination = dialog.text('Destination folder', folder=True)
        branch = dialog.text('Branch (optional)')
        recursive = dialog.check('Initialize submodules recursively')
        if dialog.submitted():
            address, target, recurse, ref = url.text(), destination.text(), recursive.isChecked(), branch.text()
            if not target.strip(): self._message('Enter a clone destination.', error=True); return
            self._job('Clone repository', lambda runner: clone(address, target, runner, recurse, ref),
                      lambda path: self.open_repository(path))

    def init_dialog(self):
        if not self._discard_draft(): return
        path = qt.QFileDialog.getExistingDirectory(self, 'Initialize Git in folder')
        if path and self._confirm('Initialize repository?', f'Create Git metadata in:\n{path}\n\nExisting files will be kept.'):
            self._job('Initialize repository', lambda runner: initialize(path, runner), lambda path: self.open_repository(path))

    def settings_dialog(self):
        dialog = FormDialog('Git settings', self, 'Use the installed Git executable. Credentials remain managed by Git helpers or your SSH agent. Git 2.40 or newer is required.')
        executable = dialog.text('Git executable', self.preferences.executable)
        if dialog.submitted():
            value = executable.text().strip() or 'git'
            def verified(result):
                self.preferences.executable = value
                self._save()
                self._message(result)
            def verify(runner):
                runner.executable = value
                return runner.version()
            self._job('Check Git executable', verify, verified)

    def manage_repositories(self):
        dialog = FormDialog('Manage repositories', self, 'Removing a bookmark keeps every repository file on disk.')
        paths = [entry['path'] for entry in self.preferences.repositories]
        choice = dialog.choice('Repository', paths)
        action = dialog.choice('Action', ['Toggle pin', 'Remove bookmark'])
        if paths and dialog.submitted():
            path = choice.currentText()
            if action.currentIndex() == 0:
                for entry in self.preferences.repositories:
                    if entry['path'] == path: entry['pinned'] = not entry['pinned']
            else:
                self.preferences.repositories = [e for e in self.preferences.repositories if e['path'] != path]
                if self.preferences.last_repository == path: self.preferences.last_repository = ''
            self._save()
            self._repositories()

    def preview_change(self, change, staged):
        if self.busy or not self.path: return
        path = self.path
        def read(runner):
            repo = Repository(path, runner)
            return repo.untracked_preview(change.path) if change.index == '?' else repo.diff(change.path, staged=staged)
        self.preview.set_file_actions(staged, change.index != '?' and not change.conflict)
        self._job('Read file changes', read, lambda text: self.preview.show_text(
            ('Staged: ' if staged else 'Working tree: ') + change.path, text or 'No textual diff. Check submodule or file-mode status.'))

    def preview_commit(self, commit):
        if self.busy or not self.path: return
        path = self.path
        full_tree = bool(self.history.file_mode.currentIndex())
        def read(runner):
            repo = Repository(path, runner)
            return repo.commit_details(commit.oid), (repo.tree(commit.oid) if full_tree else repo.commit_files(commit.oid))
        def show(result):
            text, entries = result
            self.preview.show_text(commit.oid + ' · ' + commit.subject, text)
            self.history.set_tree(entries)
            self.history.metadata.setPlainText(text.split("\ndiff --git ", 1)[0])
            self.preview.hide_file_actions()
            self.history.select_first_file()
        self._job('Read commit', read, show)

    def preview_blob(self, entry):
        if self.busy or not self.path: return
        if entry.kind == 'change':
            path = self.path
            self._job('Read commit file diff', lambda runner: Repository(path, runner).commit_file_diff(entry.oid, entry.path),
                      lambda text: self.preview.show_text(entry.path, text or 'No textual diff (binary or file mode change).'))
            return
        if entry.kind == 'commit':
            self.preview.show_text(entry.path, f'Submodule commit: {entry.oid}\nOpen its repository to browse its files.')
            return
        path = self.path
        self._job('Read historical file', lambda runner: Repository(path, runner).blob(entry.oid),
                  lambda text: self.preview.show_text(entry.path + ' · ' + entry.oid[:8], text))

    def _view_changed(self, index):
        target = self.history_preview_layout if index == 1 else self.change_preview_layout
        target.addWidget(self.preview)
        self.preview.hide_file_actions()
        self._select_navigation(index)
        if index == 1:
            if self.history.selected_commit() is None and self.history.table.topLevelItemCount():
                self.history.table.setCurrentItem(self.history.table.topLevelItem(0))
            elif self.history.selected_commit(): self.preview_commit(self.history.selected_commit())
        else:
            for tree in (self.changes.staged_files, self.changes.unstaged_files):
                item=tree.currentItem()
                if item:
                    self.preview_change(*item.data(0,qt.Qt.ItemDataRole.UserRole))
                    break
            else: self.preview.show_text('Select a changed file', '')

    def load_more(self):
        self.history_limit = min(5000, self.history_limit + 200)
        self.refresh()

    def commit(self, message, amend):
        if not message.strip():
            self._message('Enter a commit message.', error=True)
            self.changes.message.setFocus()
            return
        if amend and not self._confirm('Amend last commit?', 'Replace the current branch tip with a new commit. Published history may need coordinated recovery.'):
            return
        def committed(result):
            self.changes.message.clear()
            self.changes.amend.setChecked(False)
        self._operation('Amend commit' if amend else 'Commit staged changes', lambda repo: repo.commit(message, amend), committed)

    def discard_dialog(self, changes):
        if not changes:
            self._message('Select unstaged tracked files to discard.', error=True)
            return
        if any(c.index == '?' or c.conflict or c.original_path or c.submodule != 'N...' for c in changes):
            self._message('Discard supports ordinary tracked files. Resolve conflicts or manage untracked, renamed, and submodule files separately.', error=True)
            return
        paths = ChangesPanel.paths(changes)
        if self._confirm('Discard unstaged edits?', 'Restore these files from the index. These unstaged edits cannot be recovered through Git:\n\n' + '\n'.join(paths)):
            self._operation('Discard unstaged edits', lambda repo: repo.discard(paths))

    def fetch(self): self._operation('Fetch remotes', lambda repo: repo.fetch())

    def pull_dialog(self):
        if not self.snapshot: return
        dialog = FormDialog('Pull upstream', self, f'Current upstream: {self.snapshot.status.upstream or "not configured"}. Fetch is included. A failed merge or rebase may require conflict resolution.')
        strategy = dialog.choice('Strategy', ['Fast-forward only', 'Merge', 'Rebase'])
        if dialog.submitted():
            value = ('ff-only', 'merge', 'rebase')[strategy.currentIndex()]
            self._operation('Pull upstream', lambda repo: repo.pull(value))

    def push_dialog(self):
        if not self.snapshot: return
        status = self.snapshot.status
        if status.branch == '(detached)':
            self._message('Create or switch to a branch before pushing.', error=True)
            return
        dialog = FormDialog('Push branch', self, f'Push {status.branch}. Upstream: {status.upstream or "not configured"}. Force push is not used.')
        publish = dialog.check('Publish branch and set upstream', not bool(status.upstream))
        remote = dialog.choice('Remote for publishing', self.snapshot.remotes)
        branch = dialog.text('Remote branch for publishing', status.branch)
        if dialog.submitted():
            if publish.isChecked():
                if not remote.currentText(): self._message('Add a remote before publishing.', error=True); return
                name, target = remote.currentText(), branch.text()
                self._operation('Publish branch', lambda repo: repo.push(name, target))
            else:
                self._operation('Push branch', lambda repo: repo.push())

    def branch_dialog(self):
        dialog = FormDialog('Create branch', self)
        name = dialog.text('Branch name')
        switch = dialog.check('Switch to the new branch', True)
        commit = self.history.selected_commit()
        base = dialog.check('Start at selected history commit' + (f' ({commit.oid[:8]})' if commit else ''))
        base.setEnabled(commit is not None)
        if dialog.submitted():
            value, checkout = name.text(), switch.isChecked()
            oid = commit.oid if commit and base.isChecked() else None
            self._operation('Create branch', lambda repo: repo.create_branch(value, checkout, oid))

    def stash_dialog(self):
        dialog = FormDialog('Stash changes', self)
        message = dialog.text('Message')
        untracked = dialog.check('Include untracked files')
        if dialog.submitted():
            value, include = message.text(), untracked.isChecked()
            self._operation('Stash changes', lambda repo: repo.stash_save(value, include))

    def show_more(self):
        self.more_menu.exec(self.action_buttons['More…'].mapToGlobal(qt.QPoint(0, self.action_buttons['More…'].height())))

    def _ref_activated(self, item, column):
        value = item.data(0, qt.Qt.ItemDataRole.UserRole)
        if value and value[0] == 'submodule':
            candidate=(self.path / value[1]).resolve()
            if candidate.is_relative_to(self.path.resolve()): self.open_repository(candidate)
            else: self._message('The submodule path is outside this repository.', error=True)
        elif value and value[0] == 'subtree':
            self.repository_tools.subtree_dialog()
        elif value and value[0] == 'branch':
            self._operation('Switch branch', lambda repo: repo.switch(value[1]))

    def ref_menu(self, point):
        if self.busy: return
        item = self.refs.itemAt(point)
        value = item.data(0, qt.Qt.ItemDataRole.UserRole) if item else None
        if not value: return
        kind, name, ref = value
        menu = qt.QMenu(self)
        if kind == 'branch':
            menu.addAction('Switch branch', lambda: self._operation('Switch branch', lambda repo: repo.switch(name)))
            menu.addAction('Merge into current branch…', lambda: self._merge(name))
            menu.addAction('Rename…', lambda: self.rename_branch(name))
            menu.addAction('Set upstream…', lambda: self.upstream_dialog(name))
            menu.addAction('Delete merged branch…', lambda: self.delete_branch(name))
        elif kind == 'remote_branch' and not name.endswith('/HEAD'):
            menu.addAction('Check out tracking branch…', lambda: self.checkout_remote(name))
            menu.addAction('Merge into current branch…', lambda: self._merge(ref.name))
        elif kind == 'remote':
            menu.addAction('Fetch', lambda: self._operation('Fetch remote', lambda repo: repo.fetch(name)))
            menu.addAction('Edit URL…', lambda: self.remote_dialog(name))
            menu.addAction('Remove remote…', lambda: self.remove_remote(name))
        elif kind == 'stash':
            for action in ('apply', 'pop', 'drop'):
                menu.addAction(action.capitalize() + '…', lambda checked=False, action=action: self.stash_action(action, name))
        elif kind == 'tag':
            menu.addAction('View tag commit', lambda: self.show_ref_commit(ref))
            menu.addAction('Push tag…', lambda: self.push_tag(name))
            menu.addAction('Delete local tag…', lambda: self.delete_tag(name))
        if menu.actions(): menu.exec(self.refs.viewport().mapToGlobal(point))

    def rename_branch(self, old):
        dialog = FormDialog('Rename branch', self)
        new = dialog.text('New branch name', old)
        if dialog.submitted():
            name = new.text()
            self._operation('Rename branch', lambda repo: repo.rename_branch(old, name))

    def delete_branch(self, name):
        if self._confirm('Delete branch?', f'Delete local branch {name}? Git will refuse if it is unmerged or checked out.'):
            self._operation('Delete merged branch', lambda repo: repo.delete_branch(name))

    def upstream_dialog(self, name):
        dialog = FormDialog('Set branch upstream', self, f'Configure tracking for {name} without pushing any commits.')
        remote = dialog.choice('Remote branch', [r.name for r in self.snapshot.refs
                              if r.name.startswith('refs/remotes/') and not r.name.endswith('/HEAD')])
        if dialog.submitted() and remote.currentText():
            ref = remote.currentText()
            self._operation('Set branch upstream', lambda repo: repo.set_upstream(name, ref))

    def checkout_remote(self, ref):
        dialog = FormDialog('Create tracking branch', self)
        name = dialog.text('Local branch name', ref.split('/', 1)[1])
        if dialog.submitted():
            value = name.text()
            from ..repository import argument
            def checkout(repo):
                repo.run(['check-ref-format', '--branch', argument(value)])
                return repo.run(['switch', '-c', value, '--track', argument('refs/remotes/' + ref)])
            self._operation('Create tracking branch', checkout)

    def show_ref_commit(self, ref):
        # Tags can point to annotated tag objects: resolve to a commit first.
        path = self.path
        full_tree = bool(self.history.file_mode.currentIndex())
        def read(runner):
            repo = Repository(path, runner)
            oid = repo.run(['rev-parse', '--verify', ref.name + '^{commit}']).stdout.decode('ascii').strip()
            return oid, repo.commit_details(oid), (repo.tree(oid) if full_tree else repo.commit_files(oid))
        def show(result):
            oid, text, entries = result
            self.history.search.clear()
            self.history.branch_filter.setCurrentIndex(0)
            with qt.QSignalBlocker(self.history.table):
                self.history.table.setCurrentItem(None)
                for index in range(self.history.table.topLevelItemCount()):
                    item = self.history.table.topLevelItem(index)
                    if item.data(1, qt.Qt.ItemDataRole.UserRole).oid == oid:
                        self.history.table.setCurrentItem(item)
                        break
            self.preview.show_text(ref.name, text)
            self.history.set_tree(entries)
            self.history.metadata.setPlainText(text.split("\ndiff --git ", 1)[0])
            self.preview.hide_file_actions()
            with qt.QSignalBlocker(self.views): self.views.setCurrentIndex(1)
            self.history_preview_layout.addWidget(self.preview)
            self._select_navigation(1)
            self.history.select_first_file()
        self._job('Read reference commit', read, show)

    def stash_action(self, action, ref):
        if self._confirm(action.capitalize() + ' stash?', f'{action.capitalize()} {ref}?' + (' Dropped stashes may be difficult to recover.' if action == 'drop' else ' Conflicts may need manual resolution.')):
            self._operation(action.capitalize() + ' stash', lambda repo: repo.stash_action(action, ref))

    def remote_dialog(self, name=None):
        if name:
            path = self.path
            self._job('Read remote URL', lambda runner: Repository(path, runner).remote_details(name),
                      lambda url: self._remote_form(name, url))
        else:
            self._remote_form()

    def _remote_form(self, name=None, current_url=''):
        dialog = FormDialog('Edit remote URL' if name else 'Add remote', self)
        remote = dialog.text('Remote name', name or 'origin')
        if name: remote.setReadOnly(True)
        url = dialog.text('Repository URL or local path', current_url)
        if dialog.submitted():
            value, address = remote.text(), url.text()
            self._operation('Edit remote' if name else 'Add remote',
                            lambda repo: repo.remote_set_url(value, address) if name else repo.remote_add(value, address))

    def remove_remote(self, name):
        if self._confirm('Remove remote?', f'Remove {name} and its local tracking references? The remote repository is kept.'):
            self._operation('Remove remote', lambda repo: repo.remote_remove(name))

    def merge_dialog(self):
        if not self.snapshot: return
        dialog = FormDialog('Merge into current branch', self)
        ref = dialog.choice('Branch to merge', [r.name for r in self.snapshot.refs if not r.current and not r.name.startswith('refs/tags/')])
        if dialog.submitted() and ref.currentText(): self._merge(ref.currentText())

    def _merge(self, ref):
        if self._confirm('Merge branch?', f'Merge {ref} into {self.snapshot.status.branch}? Conflicts will appear in Changes.'):
            self._operation('Merge branch', lambda repo: repo.merge(ref))

    def cherry_pick(self): self._commit_action('Cherry-pick', lambda repo, oid: repo.cherry_pick(oid))
    def revert(self): self._commit_action('Revert', lambda repo, oid: repo.revert(oid))

    def _commit_action(self, title, callback):
        commit = self.history.selected_commit()
        if not commit: self._message('Select a commit in History first.', error=True); return
        if len(commit.parents) > 1:
            self._message('Merge commits require a mainline choice; this version supports ordinary commits.', error=True)
            return
        if self._confirm(title + ' commit?', f'{title} {commit.oid[:8]} — {commit.subject}?'):
            self._operation(title + ' commit', lambda repo: callback(repo, commit.oid))

    def finish_operation(self, abort=False):
        if not self.snapshot: return
        operation = self.snapshot.operation
        if abort and not self._confirm('Abort operation?', f'Abort the current {operation}? Git will attempt to restore its starting state.'):
            return
        self._operation(('Abort ' if abort else 'Continue ') + operation, lambda repo: repo.finish_operation(operation, abort))

    def open_folder(self):
        if self.path: qt.QDesktopServices.openUrl(qt.QUrl.fromLocalFile(str(self.path)))

    def edit_file(self, relative_path):
        if self.busy or not self.path: return
        from features import registry
        if not registry.is_feature_enabled('text_editor'):
            self._message('Enable the Text Editor feature in Settings to edit files here.', error=True)
            return
        path = (self.path / relative_path).resolve()
        if not path.is_relative_to(self.path.resolve()) or not path.is_file():
            self._message('The selected path is not a regular file within this repository.', error=True)
            return
        from features.text_editor.service import editor_service
        service = editor_service()
        if not hasattr(self, '_editor_service'):
            self._editor_service = service
            service.saved.connect(self._editor_saved)
        service.open(path)

    def _editor_saved(self, path):
        if self.path and Path(path).resolve().is_relative_to(self.path.resolve()): self.refresh()

    def compare_to_head(self):
        selected = self.history.selected_commit()
        if not selected or not self.snapshot:
            self._message('Select a commit in History first.', error=True)
            return
        first, second, path = selected.oid, self.snapshot.status.oid, self.path
        self._job('Compare revisions', lambda runner: Repository(path, runner).compare(first, second),
                  lambda text: self.preview.show_text(f'{first[:8]} → HEAD {second[:8]}', text or 'No differences.'))

    def tag_dialog(self):
        dialog = FormDialog('Create tag', self, 'Leave the message empty for a lightweight tag. Tags are created locally; use the tag context menu to push one.')
        name = dialog.text('Tag name')
        message = dialog.text('Annotation (optional)')
        selected = self.history.selected_commit()
        base = dialog.check('Tag selected history commit' + (f' ({selected.oid[:8]})' if selected else ''))
        base.setEnabled(selected is not None)
        if dialog.submitted():
            value, annotation = name.text(), message.text()
            oid = selected.oid if selected and base.isChecked() else None
            self._operation('Create tag', lambda repo: repo.create_tag(value, annotation, oid))

    def push_tag(self, name):
        dialog = FormDialog('Push tag', self, f'Publish tag {name}.')
        remote = dialog.choice('Remote', self.snapshot.remotes)
        if dialog.submitted() and remote.currentText():
            value = remote.currentText()
            self._operation('Push tag', lambda repo: repo.push_tag(value, name))

    def delete_tag(self, name):
        if self._confirm('Delete local tag?', f'Delete tag {name} locally? Any remote copy is kept.'):
            self._operation('Delete tag', lambda repo: repo.delete_tag(name))

    def reflog_dialog(self):
        path = self.path
        def show(entries):
            if not entries:
                self._message('This repository has no HEAD reflog entries.')
                return
            dialog = FormDialog('Recover from reflog', self, 'Create a branch at a previous HEAD position. This preserves the current working tree unless you choose to switch branches. Only the latest 100 HEAD entries are shown.')
            entry = dialog.choice('Reflog entry', [f'{ref} · {oid[:8]} · {message}' for oid, ref, message in entries])
            name = dialog.text('Recovery branch', 'rescue/recovered')
            switch = dialog.check('Switch to recovery branch')
            if dialog.submitted():
                oid, value, checkout = entries[entry.currentIndex()][0], name.text(), switch.isChecked()
                self._operation('Create recovery branch', lambda repo: repo.create_branch(value, checkout, oid))
        self._job('Read reflog', lambda runner: Repository(path, runner).reflog(), show)

    def identity_dialog(self):
        path = self.path
        def show(values):
            dialog = FormDialog('Repository commit identity', self, 'Save author identity in this repository’s local Git configuration. Linked worktrees share these settings. Global Git settings are kept.')
            name = dialog.text('Author name', values[0])
            email = dialog.text('Author email', values[1])
            if dialog.submitted():
                author, address = name.text(), email.text()
                self._operation('Save repository identity', lambda repo: repo.set_identity(author, address))
        self._job('Read commit identity', lambda runner: Repository(path, runner).identity(), show)
