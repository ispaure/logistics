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
        from .commands.forms import RepositoryCommands
        self.commands = RepositoryCommands(self)
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
                self.commands.dispatch('Save repository settings', 'save_settings', values,
                                       repository=path, after=self._apply_template)
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
        repository = self.path
        branch = self.snapshot.status.branch if self.snapshot else None
        if action == 'discard' and not self._confirm('Discard this hunk?',
                'Discard only these unstaged edits? They cannot be recovered through Git.'):
            return
        def applied(result):
            self._refresh_preview_pending = (context['path'], context['staged'])
        self.commands.dispatch(action.capitalize() + ' hunk', 'apply_hunk',
            context['path'], index, context['patch'], staged=context['staged'], discard=action == 'discard',
            repository=repository, branch=branch, after=applied)

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
        return self.commands.commit(message, amend)

    def discard_dialog(self, changes):
        return self.commands.discard_dialog(changes)

    def fetch(self):
        return self.commands.fetch()

    def pull_dialog(self):
        return self.commands.pull_dialog()

    def push_dialog(self):
        return self.commands.push_dialog()

    def branch_dialog(self):
        return self.commands.branch_dialog()

    def stash_dialog(self):
        return self.commands.stash_dialog()

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
            self.commands.dispatch('Switch branch', 'switch', value[1], repository=self.path)

    def ref_menu(self, point):
        return self.commands.ref_menu(point)

    def rename_branch(self, old):
        return self.commands.rename_branch(old)

    def delete_branch(self, name):
        return self.commands.delete_branch(name)

    def upstream_dialog(self, name):
        return self.commands.upstream_dialog(name)

    def checkout_remote(self, ref):
        return self.commands.checkout_remote(ref)

    def show_ref_commit(self, ref):
        return self.history_controller.show_ref_commit(ref)

    def stash_action(self, action, ref):
        return self.commands.stash_action(action, ref)

    def remote_dialog(self, name=None):
        return self.commands.remote_dialog(name)

    def _remote_form(self, name=None, current_url=''):
        return self.commands._remote_form(name, current_url)

    def remove_remote(self, name):
        return self.commands.remove_remote(name)

    def merge_dialog(self):
        return self.commands.merge_dialog()

    def _merge(self, ref):
        return self.commands._merge(ref)

    def cherry_pick(self):
        return self.commands.cherry_pick()
    def revert(self):
        return self.commands.revert()

    def _commit_action(self, title, callback):
        return self.commands._commit_action(title, callback)

    def finish_operation(self, abort=False):
        return self.commands.finish_operation(abort)

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
            from services.editors.ui.fonts import bind_code_views
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
                self.commands.dispatch('Save merge result', 'save_conflict', inputs, text,
                                       stage=stage_requested, repository=path, after=saved)
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
        from features.application import registry
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
        return self.commands.tag_dialog()

    def push_tag(self, name):
        return self.commands.push_tag(name)

    def delete_tag(self, name):
        return self.commands.delete_tag(name)

    def reflog_dialog(self):
        return self.commands.reflog_dialog()

    def identity_dialog(self):
        return self.commands.identity_dialog()
