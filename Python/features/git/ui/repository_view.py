"""Git workspace orchestration. Domain commands stay in repository.py.

One retained worker owns each operation; switching repositories, mutating actions,
and refreshes cannot overlap. Failures remain visible and trigger a fresh snapshot
after writes, including conflicts and cancelled network operations.
"""
from pathlib import Path
import sys
import shlex
from shiboken6 import isValid

from commonUtils.ui import pyside as qt
from ..preferences import Preferences
from ..repository import Repository, clone, initialize
from ..runner import redact
from .changes import ChangesPanel
from .dialogs import FormDialog
from .jobs import GitJobs
from .repository_tools import RepositoryTools
from .history_controller import RepositoryHistory


from .application_preferences import ApplicationPreferences


from .layout import RepositoryLayout


class RepositoryView(ApplicationPreferences, GitJobs, RepositoryLayout, qt.QMainWindow):
    feature_settings_requested = qt.Signal(str)
    title_changed = qt.Signal(str)
    view_title = "Repository (Git)"
    idle = qt.Signal()

    # Compatibility accessors keep job and host callbacks on one state owner.
    @property
    def history_limit(self):
        return self.history_controller.limit

    @history_limit.setter
    def history_limit(self, value):
        self.history_controller.limit = value

    @property
    def _preview_reload(self):
        return self.history_controller.reload

    @_preview_reload.setter
    def _preview_reload(self, value):
        self.history_controller.reload = value

    @property
    def _search_pending(self):
        return self.history_controller.search_pending

    @_search_pending.setter
    def _search_pending(self, value):
        self.history_controller.search_pending = value

    @property
    def _focus_search_pending(self):
        return self.history_controller.focus_pending

    @_focus_search_pending.setter
    def _focus_search_pending(self, value):
        self.history_controller.focus_pending = value

    @property
    def _comparison_selection(self):
        return self.history_controller.comparison_selection

    @_comparison_selection.setter
    def _comparison_selection(self, value):
        self.history_controller.comparison_selection = value

    def __init__(self, parent=None, *, preferences_path=None, preferences=None, repository_opener=None, restore_last=True):
        super().__init__(parent)
        self.setProperty('navigation_position', 'workspace')
        self.setProperty('navigation_order', 20)
        self.preferences = preferences or Preferences(preferences_path)
        self.repository_opener = repository_opener
        self.working_file_opener = None
        self.requested_path = None
        self.worker = None
        self.snapshot = None
        self.path = None
        self.history_controller = RepositoryHistory(self)
        self._template_message = ''
        self.closing = False
        self._refresh_pending = False
        self.repository_tools = RepositoryTools(self)
        self._build()
        self.init_preferences()
        from .menus import RepositoryMenus
        self.menu_controls = RepositoryMenus(self)
        self._repositories()
        self._set_busy(False)
        if self.preferences.warning: self._message(self.preferences.warning, error=True)
        if restore_last and self.preferences.options['restore_windows'] and self.preferences.last_repository:
            qt.QTimer.singleShot(0, self, lambda: self.open_repository(self.preferences.last_repository))

    @property
    def busy(self): return self.worker is not None

    def _set_busy(self, busy):
        if busy:
            focused = qt.QApplication.focusWidget()
            if focused is not None and self.content.isAncestorOf(focused):
                self._busy_focus = focused
        available = self.snapshot is not None
        self.repository_menu.setEnabled(not busy)
        self.toolbar.setEnabled(not busy)
        for title, button in self.action_buttons.items():
            button.defaultAction().setEnabled(not busy and (available or title == 'Settings'))
        self.content.setEnabled(available and not busy)
        self.operation_bar.setEnabled(available and not busy)
        self.cancel_button.setEnabled(busy)
        self.progress.setVisible(busy)
        if hasattr(self, 'menu_controls'):
            self.menu_controls.update(busy)
        if not busy:
            focused = getattr(self, '_busy_focus', None)
            self._busy_focus = None
            if focused is not None and isValid(focused) and focused.isVisible() and focused.isEnabled():
                focused.setFocus()

    def _message(self, text, error=False):
        self._status_error = text if error else ''
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

    def prepare_close(self):
        if not self.closing and not self.can_close():
            return False
        return super().prepare_close()

    def can_close(self):
        return self._discard_draft()

    def _discard_draft(self):
        if not self.changes.message.toPlainText().strip() or self.changes.message.toPlainText() == self._template_message: return True
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
        self.bookmark_menu.clear()
        for entry in sorted(self.preferences.repositories, key=lambda entry: not entry['pinned']):
            path = entry['path']
            self.bookmark_menu.addAction(('★ ' if entry['pinned'] else '') + path,
                                         lambda checked=False, path=path: self.open_repository(path))

    def open_repository(self, path):
        if self.busy or self.closing: return
        path = Path(path).expanduser()
        if self.repository_opener is not None and self.path is not None and path.resolve() != self.path.resolve():
            return self.repository_opener(path)
        self.requested_path = path.resolve()
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
                self._preview_reload = None
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
        # This snapshot also satisfies filesystem notifications already queued
        # by the preceding operation; do not launch a duplicate refresh later.
        self.file_timer.stop()
        operation_error = operation_error or getattr(self, '_status_error', '')
        path, limit = self.path, self.history_limit
        def render(snapshot):
            self._render(snapshot)
            if operation_error: self._message(operation_error, error=True)
        self._job('Refresh repository', lambda runner: Repository(path, runner).snapshot(limit), render)

    def _render(self, snapshot):
        self.snapshot = snapshot
        self.path = snapshot.root
        name = snapshot.display_name or snapshot.root.name
        self.view_title = name + " (Git)"
        self.title_changed.emit(self.view_title)
        self.setToolTip(str(snapshot.root))
        status = snapshot.status
        branch = status.branch if status.branch != '(detached)' else f'Detached HEAD {status.oid[:8]}'
        tracking = f' · {status.upstream} · ↑{status.ahead} ↓{status.behind}' if status.upstream else ' · no upstream'
        self.repository_label.setText(f'  {name} · {branch}{tracking}')
        self.repository_label.setToolTip(str(snapshot.root))
        self.changes.set_changes(status.changes)
        self.changes.set_push_target(status.branch, 'origin' in snapshot.remotes and status.branch not in ('', '(detached)'))
        from .chrome import action_icon
        for title, icon, count, description in (
                ('Commit', 'commit', len(status.changes), 'uncommitted files'),
                ('Pull…', 'pull', status.behind if status.upstream else 0, 'incoming commits'),
                ('Push…', 'push', status.ahead if status.upstream else 0, 'outgoing commits')):
            button = self.action_buttons[title]
            button.setProperty('badge_count', count)
            button.defaultAction().setIcon(action_icon(icon, count))
            button.defaultAction().setToolTip(f'{title} · {count} {description}')
        if not self.changes.amend.isChecked():
            self._apply_template({'template_text': snapshot.template_text if snapshot.template_configured else self.preferences.options['commit_template'] or snapshot.template_text})
        if snapshot.template_warning:
            self._append_log(snapshot.template_warning + '\n')
        self.history.head_oid = status.oid
        self.update_watch()
        self.history.uncommitted_count = len(status.changes)
        self.history.set_commits(snapshot.commits, snapshot.more_history and self.history_limit < 5000)
        self.search_results.stale = True
        if self.views.currentIndex() == 2:
            self._search_pending = True
        if self.views.currentIndex() == 1 and self.history.working_copy_is_selected():
            self.preview_working_copy()
        self._render_navigation(snapshot)
        self.operation_label.setText(f'{snapshot.operation} in progress — resolve conflicts, stage files, then Continue.')
        self.operation_bar.setVisible(snapshot.operation in ('merge', 'rebase', 'cherry-pick', 'revert'))
        self.changes.amend.setEnabled(bool(snapshot.commits) and not snapshot.operation)
        if snapshot.operation: self.changes.amend.setChecked(False)
        self._set_busy(self.busy)
        pending = getattr(self, '_refresh_preview_pending', None)
        if pending is not None:
            self._refresh_preview_pending = None
            relative, staged = pending
            change = next((change for change in status.changes if change.path == relative), None)
            if self.views.currentIndex() == 0 and change is not None:
                side = staged if (change.staged if staged else change.unstaged) else not staged
                tree = self.changes.staged_files if side else self.changes.unstaged_files
                with qt.QSignalBlocker(tree):
                    for i in range(tree.topLevelItemCount()):
                        item = tree.topLevelItem(i)
                        if item.data(0, qt.Qt.ItemDataRole.UserRole)[0].path == relative:
                            tree.setCurrentItem(item); break
                self.preview_change(change, side)
            elif self.views.currentIndex() == 0:
                self.preview.show_text(relative, 'No remaining changes.')

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
            self.views.setCurrentIndex(name)
            if name == 2:
                if self.busy:
                    self._focus_search_pending = True
                else:
                    self.search_results.search.setFocus()
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
        if self.preferences.options['select_all_commit']: self.changes.unstaged_files.selectAll()
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
        from .terminal import launch
        command = 'cd' if sys.platform == 'win32' else f'cd -- {shlex.quote(str(self.path))} && pwd'
        try:
            if launch(command, str(self.path), self.preferences.options['terminal']) is False: self._message('Terminal could not be opened.', error=True)
        except OSError as error: self._message(str(error), error=True)

    def open_dialog(self):
        path = qt.QFileDialog.getExistingDirectory(self, 'Open Git repository', self.preferences.options['project_folder'])
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
        from .settings import RepositorySettingsDialog
        if self.path is None:
            self.application_settings_dialog()
            return
        path = self.path
        def show(settings):
            dialog = RepositorySettingsDialog(settings, self)
            if dialog.exec() == qt.QDialog.DialogCode.Accepted:
                values = dialog.values()
                self._operation('Save repository settings', lambda repo: repo.save_settings(values),
                                lambda result: self._apply_template(result))
        self._job('Read repository settings', lambda runner: Repository(path, runner).settings(), show)

    def _apply_template(self, settings):
        message = self.changes.message.toPlainText()
        if not message.strip() or message == self._template_message:
            self._template_message = settings['template_text']
            self.changes.message.setPlainText(self._template_message)

    def executable_dialog(self):
        dialog = FormDialog('Git executable', self, scope='personal')
        executable = dialog.text('Git executable', self.preferences.executable)
        executable.setToolTip('Git 2.40 or newer. Authentication uses Git helpers or SSH agents.')
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
        return self.history_controller.preview_change(change, staged)

    def apply_hunk(self, context, index, action):
        if self.busy or not self.path or str(self.path) != context['root'] or not context['allowed']: return
        if action == 'discard' and not self._confirm('Discard this hunk?',
                'Discard only these unstaged edits? They cannot be recovered through Git.'):
            return
        def applied(result):
            self._refresh_preview_pending = (context['path'], context['staged'])
        self._operation(action.capitalize() + ' hunk', lambda repo: repo.apply_hunk(
            context['path'], index, context['patch'], staged=context['staged'], discard=action == 'discard'), applied)

    def compare_change(self):
        return self.history_controller.compare_change()

    def _reload_preview(self, *args):
        return self.history_controller._reload_preview(*args)

    def preview_commit(self, commit, panel=None):
        return self.history_controller.preview_commit(commit, panel)

    def focus_parent(self, oid):
        return self.history_controller.focus_parent(oid)

    def preview_blob(self, entry):
        return self.history_controller.preview_blob(entry)

    def _view_changed(self, index):
        return self.history_controller._view_changed(index)

    def preview_working_copy(self):
        return self.history_controller.preview_working_copy()

    def preview_working_file(self, change):
        return self.history_controller.preview_working_file(change)

    def search_history(self):
        return self.history_controller.search_history()

    def _search_parent(self, oid):
        return self.history_controller._search_parent(oid)

    def load_more_search(self):
        return self.history_controller.load_more_search()

    def load_more(self):
        return self.history_controller.load_more()

    def commit(self, message, amend):
        if not message.strip():
            self._message('Enter a commit message.', error=True)
            self.changes.message.setFocus()
            return
        if amend and not self._confirm('Amend last commit?', 'Replace the current branch tip with a new commit. Published history may need coordinated recovery.'):
            return
        push = self.changes.push_immediately.isChecked()
        branch = self.snapshot.status.branch if self.snapshot else ''
        def action(repo):
            if push and repo.status().branch != branch:
                from ..runner import GitError
                raise GitError('The active branch changed. Refresh before committing and pushing.')
            return repo.commit(message, amend)
        def committed(result):
            self.changes.message.clear()
            self.changes.amend.setChecked(False)
            if push:
                self._operation('Push committed changes', lambda repo: repo.push_current_to_origin(branch))
        self._operation('Amend commit' if amend else 'Commit staged changes', action, committed)

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
        strategy.setCurrentIndex(('ff-only', 'merge', 'rebase').index(self.preferences.options['pull_strategy']))
        if dialog.submitted():
            value = ('ff-only', 'merge', 'rebase')[strategy.currentIndex()]
            self._operation('Pull upstream', lambda repo: repo.pull(value))

    def push_dialog(self):
        if not self.snapshot: return
        status = self.snapshot.status
        if status.branch == '(detached)':
            self._message('Create or switch to a branch before pushing.', error=True)
            return
        dialog = FormDialog('Push branch', self, f'Push {status.branch}. Upstream: {status.upstream or "not configured"}.')
        force = dialog.check('Force push with lease')
        force.setVisible(self.preferences.options['allow_force_push'])
        publish = dialog.check('Publish branch and set upstream', not bool(status.upstream))
        remote = dialog.choice('Remote for publishing', self.snapshot.remotes)
        branch = dialog.text('Remote branch for publishing', status.branch)
        if dialog.submitted():
            forced = force.isChecked() and self.preferences.options['allow_force_push']
            if forced and not self._confirm('Force push with lease?', 'Replace remote branch history only if its tip matches the last fetched state?'): return
            if publish.isChecked():
                if not remote.currentText(): self._message('Add a remote before publishing.', error=True); return
                name, target = remote.currentText(), branch.text()
                self._operation('Publish branch', lambda repo: repo.push(name, target, force_with_lease=forced))
            else:
                self._operation('Push branch', lambda repo: repo.push(force_with_lease=forced))

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
        self.more_menu.exec(qt.QCursor.pos())

    def _ref_activated(self, item, column):
        value = item.data(0, qt.Qt.ItemDataRole.UserRole)
        if value and value[0] == 'submodule':
            candidate=(self.path / value[1]).resolve()
            if candidate.is_relative_to(self.path.resolve()): self.open_repository(candidate)
            else: self._message('The submodule path is outside this repository.', error=True)
        elif value and value[0] == 'subtree':
            self.repository_tools.subtree_dialog()
        elif value and value[0] == 'branch':
            if self.preferences.options['confirm_switch'] and self.snapshot and not self.snapshot.status.changes and not self._confirm('Switch branch?', f'Switch to {value[1]}?'): return
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
        return self.history_controller.show_ref_commit(ref)

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

    def resolve_conflict(self, relative_path):
        if self.busy or not self.path:
            return
        from commonUtils.persistence.merge import merge_text
        from commonUtils.ui.code_editor.merge import MergeDialog
        path = self.path
        def read(runner):
            inputs = Repository(path, runner).conflict_inputs(relative_path)
            return inputs, merge_text(inputs.base, inputs.left, inputs.right)
        def opened(payload):
            inputs, model = payload
            if self.path != path or self.closing:
                return
            rebase = inputs.operation == 'rebase'
            dialog = MergeDialog(model, self, path=inputs.path,
                left_name='Index stage 2 — rebased onto' if rebase else 'Index stage 2 — current branch',
                right_name='Index stage 3 — commit being replayed' if rebase else 'Index stage 3 — incoming changes')
            from features.code_font import bind_code_views
            bind_code_views(dialog)
            stage = qt.QCheckBox('Stage resolved file after saving', dialog)
            dialog.layout().insertWidget(1, stage)
            def apply(text):
                if self.busy or self.path != path or self.closing:
                    raise ValueError('Repository changed or is busy. Reopen the merge.')
                stage_requested = stage.isChecked()
                dialog.applying = True
                dialog.widget.setEnabled(False); stage.setEnabled(False)
                dialog.apply_button.setEnabled(False)
                dialog.widget.status.setText('Saving merge result…')
                def saved(result):
                    from shiboken6 import isValid
                    if isValid(dialog):
                        dialog.applying = False
                        dialog.accept()
                self._operation('Save merge result', lambda repo: repo.save_conflict(inputs, text, stage=stage_requested), saved)
                return False
            def finished():
                from shiboken6 import isValid
                if isValid(dialog) and dialog.applying:
                    dialog.applying = False
                    dialog.widget.setEnabled(True); stage.setEnabled(True)
                    dialog._ready()
                    dialog.widget.status.setText(self.status.text())
            self.idle.connect(finished)
            def disconnected():
                from shiboken6 import isValid
                if isValid(self):
                    self.idle.disconnect(finished)
            dialog.destroyed.connect(disconnected)
            dialog.apply_callback = apply; dialog._ready()
            dialog.show()
        self._job('Read merge inputs', read, opened)

    def edit_file(self, relative_path):
        if self.busy or not self.path: return
        path = (self.path / relative_path).resolve()
        if not path.is_relative_to(self.path.resolve()) or not path.is_file():
            self._message('The selected path is not a regular file within this repository.', error=True)
            return
        if self.working_file_opener and self.working_file_opener(path):
            return
        from features import registry
        if not registry.is_feature_enabled('text_editor'):
            self._message('Enable the Text Editor feature in Settings to edit files outside registered IDE projects.', error=True)
            return
        from features.text_editor.ui.service import editor_service
        service = editor_service()
        if not hasattr(self, '_editor_service'):
            self._editor_service = service
            service.saved.connect(self._editor_saved)
        service.open(path)

    def _editor_saved(self, path):
        if self.path and Path(path).resolve().is_relative_to(self.path.resolve()): self.refresh()

    def compare_to_head(self):
        return self.history_controller.compare_to_head()

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
