"""Git workspace orchestration. Domain commands stay in repository.py.

One retained worker owns each operation; switching repositories, mutating actions,
and refreshes cannot overlap. Failures remain visible and trigger a fresh snapshot
after writes, including conflicts and cancelled network operations.
"""
from pathlib import Path

from commonUtils.ui import pyside as qt
from ..preferences import Preferences
from ..repository import Repository, clone, initialize
from ..runner import CommandResult, redact
from .changes import ChangesPanel
from .dialogs import FormDialog
from .history import HistoryPanel
from .preview import Preview
from .worker import GitWorker


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
        self._build()
        self._repositories()
        self._set_busy(False)
        if self.preferences.warning: self._message(self.preferences.warning, error=True)
        if self.preferences.last_repository:
            qt.QTimer.singleShot(0, self, lambda: self.open_repository(self.preferences.last_repository))

    def _build(self):
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        row = qt.QHBoxLayout()
        self.repositories = qt.QComboBox()
        self.repositories.setMinimumWidth(220)
        self.repositories.setAccessibleName('Git repositories')
        self.repositories.currentIndexChanged.connect(self._repository_selected)
        row.addWidget(self.repositories, 1)
        self.global_buttons = []
        for title, callback in (('Open…', self.open_dialog), ('Clone…', self.clone_dialog),
                                ('Init…', self.init_dialog), ('Repositories…', self.manage_repositories),
                                ('Git settings…', self.settings_dialog)):
            button = qt.QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
            self.global_buttons.append(button)
        layout.addLayout(row)
        self.repository_label = qt.QLabel('Open an existing repository, clone one, or initialize a folder.')
        self.repository_label.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.repository_label.setTextInteractionFlags(qt.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.repository_label.setWordWrap(True)
        layout.addWidget(self.repository_label)
        self.toolbar = qt.QWidget()
        actions = qt.QHBoxLayout(self.toolbar)
        actions.setContentsMargins(0, 0, 0, 0)
        self.action_buttons = {}
        for title, callback in (('Refresh', self.refresh), ('Fetch', self.fetch), ('Pull…', self.pull_dialog),
                                ('Push…', self.push_dialog), ('Branch…', self.branch_dialog),
                                ('Stash…', self.stash_dialog), ('More…', self.show_more)):
            button = qt.QPushButton(title)
            button.clicked.connect(callback)
            actions.addWidget(button)
            self.action_buttons[title] = button
        actions.addStretch()
        layout.addWidget(self.toolbar)
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
        self.refs = qt.QTreeWidget()
        self.refs.setHeaderLabels(['Repository'])
        self.refs.setMinimumWidth(150)
        self.refs.setAccessibleName('Repository references')
        self.refs.itemDoubleClicked.connect(self._ref_activated)
        self.refs.setContextMenuPolicy(qt.Qt.ContextMenuPolicy.CustomContextMenu)
        self.refs.customContextMenuRequested.connect(self.ref_menu)
        self.content.addWidget(self.refs)
        self.views = qt.QTabWidget()
        self.changes = ChangesPanel()
        self.history = HistoryPanel()
        self.views.addTab(self.changes, 'Changes')
        self.views.addTab(self.history, 'History')
        self.content.addWidget(self.views)
        self.preview = Preview()
        self.content.addWidget(self.preview)
        self.content.setSizes([190, 470, 520])
        self.content.setStretchFactor(0, 0)
        self.content.setStretchFactor(1, 1)
        self.content.setStretchFactor(2, 1)
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
        self.log.setAccessibleName('Git operation log')
        self.log.setMaximumBlockCount(1500)
        self.log.setMaximumHeight(170)
        self.log.hide()
        self.log_toggle.toggled.connect(self.log.setVisible)
        layout.addWidget(self.log)
        self.more_menu = qt.QMenu(self)
        for title, callback in (('Merge branch…', self.merge_dialog), ('Cherry-pick selected commit…', self.cherry_pick),
                                ('Revert selected commit…', self.revert), ('Add remote…', self.remote_dialog),
                                ('Worktrees…', self.worktrees_dialog), ('Submodules…', self.submodules_dialog),
                                ('Subtrees…', self.subtree_dialog), ('Open repository folder', self.open_folder)):
            self.more_menu.addAction(title, callback)

    @property
    def busy(self): return self.worker is not None

    def _set_busy(self, busy):
        available = self.snapshot is not None
        self.repositories.setEnabled(not busy)
        for button in self.global_buttons: button.setEnabled(not busy)
        self.toolbar.setEnabled(available and not busy)
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
        cursor.insertText(redact(text)[-65536:])
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
        if refresh and self.path and not self.busy:
            # Refresh even after failure: merge conflicts and cancellation can
            # leave valid new repository state. Keep the operation error visible.
            self._refresh(error)
        if not self.busy: self.idle.emit()

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
        if self.path and not self.busy and not self.closing: self._refresh()

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
        self.repository_label.setText(f'{snapshot.root}\n{branch}{tracking}')
        self.changes.set_changes(status.changes)
        self.history.set_commits(snapshot.commits, snapshot.more_history and self.history_limit < 5000)
        self.views.setTabText(0, f'Changes ({len(status.changes)})')
        with qt.QSignalBlocker(self.refs):
            self.refs.clear()
            groups = {name: qt.QTreeWidgetItem([name]) for name in ('Local branches', 'Remote branches', 'Tags', 'Remotes', 'Stashes')}
            for group in groups.values(): self.refs.addTopLevelItem(group)
            for ref in snapshot.refs:
                if ref.name.startswith('refs/heads/'):
                    kind, group, name = 'branch', 'Local branches', ref.name[len('refs/heads/'):]
                elif ref.name.startswith('refs/remotes/'):
                    kind, group, name = 'remote_branch', 'Remote branches', ref.name[len('refs/remotes/'):]
                else:
                    kind, group, name = 'tag', 'Tags', ref.name[len('refs/tags/'):]
                item = qt.QTreeWidgetItem([('● ' if ref.current else '') + name])
                item.setData(0, qt.Qt.ItemDataRole.UserRole, (kind, name, ref))
                item.setToolTip(0, ref.name + ('\nUpstream: ' + ref.upstream if ref.upstream else ''))
                groups[group].addChild(item)
            for remote in snapshot.remotes:
                item = qt.QTreeWidgetItem([remote])
                item.setData(0, qt.Qt.ItemDataRole.UserRole, ('remote', remote, None))
                groups['Remotes'].addChild(item)
            for ref, message in snapshot.stashes:
                item = qt.QTreeWidgetItem([message])
                item.setData(0, qt.Qt.ItemDataRole.UserRole, ('stash', ref, None))
                groups['Stashes'].addChild(item)
            for group in groups.values(): group.setExpanded(True)
        self.operation_label.setText(f'{snapshot.operation} in progress — resolve conflicts, stage files, then Continue.')
        self.operation_bar.setVisible(snapshot.operation in ('merge', 'rebase', 'cherry-pick', 'revert'))
        self.changes.amend.setEnabled(bool(snapshot.commits) and not snapshot.operation)
        if snapshot.operation: self.changes.amend.setChecked(False)
        self._set_busy(self.busy)

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
        self._job('Read file changes', read, lambda text: self.preview.show_text(
            ('Staged: ' if staged else 'Working tree: ') + change.path, text or 'No textual diff. Check submodule or file-mode status.'))

    def preview_commit(self, commit):
        if self.busy or not self.path: return
        path = self.path
        def read(runner):
            repo = Repository(path, runner)
            return repo.commit_details(commit.oid), repo.tree(commit.oid)
        def show(result):
            text, entries = result
            self.preview.show_text(commit.oid + ' · ' + commit.subject, text)
            self.history.set_tree(entries)
        self._job('Read commit', read, show)

    def preview_blob(self, entry):
        if self.busy or not self.path: return
        if entry.kind == 'commit':
            self.preview.show_text(entry.path, f'Submodule commit: {entry.oid}\nOpen its repository to browse its files.')
            return
        path = self.path
        self._job('Read historical file', lambda runner: Repository(path, runner).blob(entry.oid),
                  lambda text: self.preview.show_text(entry.path + ' · ' + entry.oid[:8], text))

    def _view_changed(self, index):
        if index == 1 and self.history.selected_commit() is None and self.history.table.topLevelItemCount():
            self.history.table.setCurrentItem(self.history.table.topLevelItem(0))

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
        if dialog.submitted():
            value, checkout = name.text(), switch.isChecked()
            self._operation('Create branch', lambda repo: repo.create_branch(value, checkout))

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
        if value and value[0] == 'branch':
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

    def checkout_remote(self, ref):
        dialog = FormDialog('Create tracking branch', self)
        name = dialog.text('Local branch name', ref.split('/', 1)[1])
        if dialog.submitted():
            value = name.text()
            from ..repository import argument
            def checkout(repo):
                repo.run(['check-ref-format', '--branch', argument(value)])
                return repo.run(['switch', '-c', value, '--track', argument(ref)])
            self._operation('Create tracking branch', checkout)

    def show_ref_commit(self, ref):
        # Tags can point to annotated tag objects: resolve to a commit first.
        path = self.path
        def read(runner):
            repo = Repository(path, runner)
            oid = repo.run(['rev-parse', '--verify', ref.name + '^{commit}']).stdout.decode('ascii').strip()
            return repo.commit_details(oid), repo.tree(oid)
        def show(result):
            self.preview.show_text(ref.name, result[0])
            self.history.set_tree(result[1])
            self.views.setCurrentIndex(1)
        self._job('Read tag commit', read, show)

    def stash_action(self, action, ref):
        if self._confirm(action.capitalize() + ' stash?', f'{action.capitalize()} {ref}?' + (' Dropped stashes may be difficult to recover.' if action == 'drop' else ' Conflicts may need manual resolution.')):
            self._operation(action.capitalize() + ' stash', lambda repo: repo.stash_action(action, ref))

    def remote_dialog(self, name=None):
        dialog = FormDialog('Edit remote URL' if name else 'Add remote', self)
        remote = dialog.text('Remote name', name or 'origin')
        if name: remote.setReadOnly(True)
        url = dialog.text('Repository URL or local path')
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

    def worktrees_dialog(self):
        path = self.path
        def show(entries):
            dialog = FormDialog('Worktrees', self, '\n'.join(f'{e.get("worktree", "")} — {e.get("branch", "detached")}' for e in entries))
            operation = dialog.choice('Action', ['Open worktree', 'Add worktree for existing branch'])
            existing = dialog.choice('Existing worktree', [e['worktree'] for e in entries if 'worktree' in e])
            destination = dialog.text('New worktree folder', folder=True)
            branch = dialog.choice('Existing branch', [r.name[len('refs/heads/'):] for r in self.snapshot.refs if r.name.startswith('refs/heads/')])
            if dialog.submitted():
                if operation.currentIndex() == 0: self.open_repository(existing.currentText())
                else:
                    target, name = destination.text(), branch.currentText()
                    if not target.strip(): self._message('Enter a worktree destination.', error=True); return
                    self._operation('Add worktree', lambda repo: repo.add_worktree(target, name))
        self._job('List worktrees', lambda runner: Repository(path, runner).worktrees(), show)

    def submodules_dialog(self):
        path = self.path
        def show(text):
            dialog = FormDialog('Submodules', self, text or 'No submodules. Updates check out the commits recorded by the parent repository.')
            operation = dialog.choice('Action', ['Initialize/update recursively', 'Add submodule', 'Open submodule folder'])
            url = dialog.text('URL for new submodule')
            destination = dialog.text('Relative submodule path')
            if dialog.submitted():
                action, address, target = operation.currentIndex(), url.text(), destination.text()
                if action == 0: self._operation('Update submodules', lambda repo: repo.update_submodules())
                elif action == 1: self._operation('Add submodule', lambda repo: repo.add_submodule(address, target))
                else:
                    candidate = (self.path / target).resolve()
                    if not target or not candidate.is_relative_to(self.path.resolve()):
                        self._message('Choose a submodule path within this repository.', error=True)
                    else: self.open_repository(candidate)
        self._job('Read submodule status', lambda runner: Repository(path, runner).submodules(), show)

    def subtree_dialog(self):
        path = self.path
        def show(result):
            if result.returncode not in (0, 129) or 'git subtree' not in (result.stdout.decode('utf-8', 'replace') + result.stderr):
                self._message('git subtree is unavailable in this Git installation.', error=True)
                return
            dialog = FormDialog('Subtrees', self, 'Add, pull, or push a repository at a relative directory prefix. Git must have a clean working tree. Successful mappings are remembered locally.')
            saved = self.preferences.subtrees.get(str(path), [])
            saved = [v for v in saved if isinstance(v, dict) and all(isinstance(v.get(k), str) for k in ('prefix', 'url', 'branch'))]
            mapping = dialog.choice('Saved mapping', ['New mapping', *(v['prefix'] for v in saved)])
            action = dialog.choice('Action', ['add', 'pull', 'push'])
            prefix = dialog.text('Directory prefix')
            url = dialog.text('Upstream URL')
            branch = dialog.text('Upstream branch', 'main')
            squash = dialog.check('Squash imported history')
            def populate(index):
                if index:
                    value = saved[index - 1]
                    prefix.setText(value['prefix']); url.setText(value['url']); branch.setText(value['branch'])
                    squash.setChecked(bool(value.get('squash')))
            mapping.currentIndexChanged.connect(populate)
            if dialog.submitted():
                operation = action.currentText()
                value = {'prefix': prefix.text(), 'url': url.text(), 'branch': branch.text(), 'squash': squash.isChecked()}
                if operation == 'push' and not self._confirm('Push subtree?', f'Publish {value["prefix"]} to {value["url"]}, branch {value["branch"]}?'):
                    return
                def remember(result):
                    self.preferences.subtrees[str(path)] = [value, *(v for v in saved if v['prefix'] != value['prefix'])]
                    self._save()
                self._operation('Subtree ' + operation, lambda repo: repo.subtree(operation, value['prefix'], value['url'], value['branch'], value['squash']), remember)
        self._job('Check subtree availability', lambda runner: runner.run(['subtree', '-h'], check=False), show)
