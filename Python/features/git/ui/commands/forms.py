"""Forms collect immutable operation inputs; GitJobs owns execution and refresh."""
from commonUtils.ui import pyside as qt
from ...repository import Repository
from ..changes import ChangesPanel
from ..dialogs import FormDialog
from .requests import GitCommand


class RepositoryCommands:
    def __init__(self, view):
        self.view = view

    def dispatch(self, label, method, *args, repository=None, branch=None, after=None, **kwargs):
        view = self.view
        repository = repository if repository is not None else view.path
        if repository is None or view.closing or view.path != repository:
            return False
        sensitive = method in {'commit', 'push', 'push_current_to_origin', 'pull', 'merge',
                               'cherry_pick', 'revert', 'finish_operation', 'discard', 'stash_save',
                               'stash_action', 'create_branch', 'create_tag', 'switch', 'checkout_tracking',
                               'stage', 'unstage', 'apply_hunk', 'save_conflict'}
        if sensitive and branch is None:
            snapshot = getattr(view, 'snapshot', None)
            branch = snapshot.status.branch if snapshot is not None else None
        request = GitCommand.capture(repository, label, method, args, kwargs,
                                     expected_branch=branch if sensitive else None)
        def completed(result):
            if not view.closing and view.path == request.repository and after is not None:
                after(result)
        return view._operation(label, request.execute, completed if after is not None else None)

    def commit(self, message, amend):
        view = self.view
        captured_path = view.path
        captured_branch = view.snapshot.status.branch if view.snapshot else None
        if not message.strip():
            view._message('Enter a commit message.', error=True)
            view.changes.message.setFocus()
            return
        if amend and not view._confirm('Amend last commit?', 'Replace the current branch tip with a new commit. Published history may need coordinated recovery.'):
            return
        push = view.changes.push_immediately.isChecked()
        branch = view.snapshot.status.branch if view.snapshot else ''
        def committed(result):
            view.changes.message.clear()
            view.changes.amend.setChecked(False)
            if push:
                self.dispatch('Push committed changes', 'push_current_to_origin', branch, repository=captured_path, branch=captured_branch)
        self.dispatch('Amend commit' if amend else 'Commit staged changes', 'commit', message, amend,
                      after=committed, repository=captured_path, branch=captured_branch)


    def discard_dialog(self, changes):
        view = self.view
        captured_path = view.path
        captured_branch = view.snapshot.status.branch if view.snapshot else None
        if not changes:
            view._message('Select unstaged tracked files to discard.', error=True)
            return
        if any(c.index == '?' or c.conflict or c.original_path or c.submodule != 'N...' for c in changes):
            view._message('Discard supports ordinary tracked files. Resolve conflicts or manage untracked, renamed, and submodule files separately.', error=True)
            return
        paths = ChangesPanel.paths(changes)
        if view._confirm('Discard unstaged edits?', 'Restore these files from the index. These unstaged edits cannot be recovered through Git:\n\n' + '\n'.join(paths)):
            self.dispatch('Discard unstaged edits', 'discard', paths, repository=captured_path, branch=captured_branch)


    def fetch(self):
        view = self.view
        captured_path = view.path
        captured_branch = view.snapshot.status.branch if view.snapshot else None
        self.dispatch('Fetch remotes', 'fetch', repository=captured_path, branch=captured_branch)



    def pull_dialog(self):
        view = self.view
        captured_path = view.path
        captured_branch = view.snapshot.status.branch if view.snapshot else None
        if not view.snapshot: return
        dialog = FormDialog('Pull upstream', view, f'Current upstream: {view.snapshot.status.upstream or "not configured"}. Fetch is included. A failed merge or rebase may require conflict resolution.')
        strategy = dialog.choice('Strategy', ['Fast-forward only', 'Merge', 'Rebase'])
        strategy.setCurrentIndex(('ff-only', 'merge', 'rebase').index(view.preferences.options['pull_strategy']))
        if dialog.submitted():
            value = ('ff-only', 'merge', 'rebase')[strategy.currentIndex()]
            self.dispatch('Pull upstream', 'pull', value, repository=captured_path, branch=captured_branch)


    def push_dialog(self):
        view = self.view
        captured_path = view.path
        captured_branch = view.snapshot.status.branch if view.snapshot else None
        if not view.snapshot: return
        status = view.snapshot.status
        if status.branch == '(detached)':
            view._message('Create or switch to a branch before pushing.', error=True)
            return
        dialog = FormDialog('Push branch', view, f'Push {status.branch}. Upstream: {status.upstream or "not configured"}.')
        force = dialog.check('Force push with lease')
        force.setVisible(view.preferences.options['allow_force_push'])
        publish = dialog.check('Publish branch and set upstream', not bool(status.upstream))
        remote = dialog.choice('Remote for publishing', view.snapshot.remotes)
        branch = dialog.text('Remote branch for publishing', status.branch)
        if dialog.submitted():
            forced = force.isChecked() and view.preferences.options['allow_force_push']
            if forced and not view._confirm('Force push with lease?', 'Replace remote branch history only if its tip matches the last fetched state?'): return
            if publish.isChecked():
                if not remote.currentText(): view._message('Add a remote before publishing.', error=True); return
                name, target = remote.currentText(), branch.text()
                self.dispatch('Publish branch', 'push', name, target, force_with_lease=forced, repository=captured_path, branch=captured_branch)
            else:
                self.dispatch('Push branch', 'push', force_with_lease=forced, repository=captured_path, branch=captured_branch)


    def branch_dialog(self):
        view = self.view
        captured_path = view.path
        captured_branch = view.snapshot.status.branch if view.snapshot else None
        dialog = FormDialog('Create branch', view)
        name = dialog.text('Branch name')
        switch = dialog.check('Switch to the new branch', True)
        commit = view.history.selected_commit()
        base = dialog.check('Start at selected history commit' + (f' ({commit.oid[:8]})' if commit else ''))
        base.setEnabled(commit is not None)
        if dialog.submitted():
            value, checkout = name.text(), switch.isChecked()
            oid = commit.oid if commit and base.isChecked() else None
            self.dispatch('Create branch', 'create_branch', value, checkout, oid, repository=captured_path, branch=captured_branch)


    def stash_dialog(self):
        view = self.view
        captured_path = view.path
        captured_branch = view.snapshot.status.branch if view.snapshot else None
        dialog = FormDialog('Stash changes', view)
        message = dialog.text('Message')
        untracked = dialog.check('Include untracked files')
        if dialog.submitted():
            value, include = message.text(), untracked.isChecked()
            self.dispatch('Stash changes', 'stash_save', value, include, repository=captured_path, branch=captured_branch)


    def ref_menu(self, point):
        view = self.view
        captured_path = view.path
        captured_branch = view.snapshot.status.branch if view.snapshot else None
        if view.busy: return
        item = view.refs.itemAt(point)
        value = item.data(0, qt.Qt.ItemDataRole.UserRole) if item else None
        if not value: return
        kind, name, ref = value
        def invoke(callback, *args):
            snapshot = view.snapshot
            if (view.closing or view.path != captured_path
                    or (snapshot.status.branch if snapshot else None) != captured_branch):
                return
            return callback(*args)
        menu = qt.QMenu(view)
        if kind == 'branch':
            menu.addAction('Switch branch', lambda: self.dispatch('Switch branch', 'switch', name, repository=captured_path, branch=captured_branch))
            menu.addAction('Merge into current branch…', lambda: invoke(view._merge, name))
            menu.addAction('Rename…', lambda: invoke(view.rename_branch, name))
            menu.addAction('Set upstream…', lambda: invoke(view.upstream_dialog, name))
            menu.addAction('Delete merged branch…', lambda: invoke(view.delete_branch, name))
        elif kind == 'remote_branch' and not name.endswith('/HEAD'):
            menu.addAction('Check out tracking branch…', lambda: invoke(view.checkout_remote, name))
            menu.addAction('Merge into current branch…', lambda: invoke(view._merge, ref.name))
        elif kind == 'remote':
            menu.addAction('Fetch', lambda: self.dispatch('Fetch remote', 'fetch', name, repository=captured_path, branch=captured_branch))
            menu.addAction('Edit URL…', lambda: invoke(view.remote_dialog, name))
            menu.addAction('Remove remote…', lambda: invoke(view.remove_remote, name))
        elif kind == 'stash':
            for action in ('apply', 'pop', 'drop'):
                menu.addAction(action.capitalize() + '…', lambda checked=False, action=action: invoke(view.stash_action, action, name))
        elif kind == 'tag':
            menu.addAction('View tag commit', lambda: invoke(view.show_ref_commit, ref))
            menu.addAction('Push tag…', lambda: invoke(view.push_tag, name))
            menu.addAction('Delete local tag…', lambda: invoke(view.delete_tag, name))
        if menu.actions(): menu.exec(view.refs.viewport().mapToGlobal(point))


    def rename_branch(self, old):
        view = self.view
        captured_path = view.path
        captured_branch = view.snapshot.status.branch if view.snapshot else None
        dialog = FormDialog('Rename branch', view)
        new = dialog.text('New branch name', old)
        if dialog.submitted():
            name = new.text()
            self.dispatch('Rename branch', 'rename_branch', old, name, repository=captured_path, branch=captured_branch)


    def delete_branch(self, name):
        view = self.view
        captured_path = view.path
        captured_branch = view.snapshot.status.branch if view.snapshot else None
        if view._confirm('Delete branch?', f'Delete local branch {name}? Git will refuse if it is unmerged or checked out.'):
            self.dispatch('Delete merged branch', 'delete_branch', name, repository=captured_path, branch=captured_branch)


    def upstream_dialog(self, name):
        view = self.view
        captured_path = view.path
        captured_branch = view.snapshot.status.branch if view.snapshot else None
        dialog = FormDialog('Set branch upstream', view, f'Configure tracking for {name} without pushing any commits.')
        remote = dialog.choice('Remote branch', [r.name for r in view.snapshot.refs
                              if r.name.startswith('refs/remotes/') and not r.name.endswith('/HEAD')])
        if dialog.submitted() and remote.currentText():
            ref = remote.currentText()
            self.dispatch('Set branch upstream', 'set_upstream', name, ref, repository=captured_path, branch=captured_branch)


    def checkout_remote(self, ref):
        view = self.view
        captured_path = view.path
        captured_branch = view.snapshot.status.branch if view.snapshot else None
        dialog = FormDialog('Create tracking branch', view)
        name = dialog.text('Local branch name', ref.split('/', 1)[1])
        if dialog.submitted():
            value = name.text()
            self.dispatch('Create tracking branch', 'checkout_tracking', value, ref, repository=captured_path, branch=captured_branch)


    def stash_action(self, action, ref):
        view = self.view
        captured_path = view.path
        captured_branch = view.snapshot.status.branch if view.snapshot else None
        if view._confirm(action.capitalize() + ' stash?', f'{action.capitalize()} {ref}?' + (' Dropped stashes may be difficult to recover.' if action == 'drop' else ' Conflicts may need manual resolution.')):
            self.dispatch(action.capitalize() + ' stash', 'stash_action', action, ref, repository=captured_path, branch=captured_branch)


    def remote_dialog(self, name=None):
        view = self.view
        captured_path = view.path
        captured_branch = view.snapshot.status.branch if view.snapshot else None
        if name:
            path = view.path
            view._job('Read remote URL', lambda runner: Repository(path, runner).remote_details(name),
                      lambda url: view._remote_form(name, url) if view.path == captured_path and not view.closing else None)
        else:
            view._remote_form()


    def _remote_form(self, name=None, current_url=''):
        view = self.view
        captured_path = view.path
        captured_branch = view.snapshot.status.branch if view.snapshot else None
        dialog = FormDialog('Edit remote URL' if name else 'Add remote', view)
        remote = dialog.text('Remote name', name or 'origin')
        if name: remote.setReadOnly(True)
        url = dialog.text('Repository URL or local path', current_url)
        if dialog.submitted():
            value, address = remote.text(), url.text()
            self.dispatch('Edit remote' if name else 'Add remote', 'remote_set_url' if name else 'remote_add',
                          value, address, repository=captured_path)


    def remove_remote(self, name):
        view = self.view
        captured_path = view.path
        captured_branch = view.snapshot.status.branch if view.snapshot else None
        if view._confirm('Remove remote?', f'Remove {name} and its local tracking references? The remote repository is kept.'):
            self.dispatch('Remove remote', 'remote_remove', name, repository=captured_path, branch=captured_branch)


    def merge_dialog(self):
        view = self.view
        captured_path = view.path
        captured_branch = view.snapshot.status.branch if view.snapshot else None
        if not view.snapshot: return
        dialog = FormDialog('Merge into current branch', view)
        ref = dialog.choice('Branch to merge', [r.name for r in view.snapshot.refs if not r.current and not r.name.startswith('refs/tags/')])
        if dialog.submitted() and ref.currentText():
            self._merge(ref.currentText(), repository=captured_path, branch=captured_branch)


    def _merge(self, ref, *, repository=None, branch=None):
        view = self.view
        captured_path = repository if repository is not None else view.path
        captured_branch = branch if branch is not None else view.snapshot.status.branch if view.snapshot else None
        if view.closing or view.path != captured_path:
            return
        if view._confirm('Merge branch?', f'Merge {ref} into {captured_branch}? Conflicts will appear in Changes.'):
            self.dispatch('Merge branch', 'merge', ref, repository=captured_path, branch=captured_branch)


    def cherry_pick(self):
        view = self.view
        captured_path = view.path
        captured_branch = view.snapshot.status.branch if view.snapshot else None
        view._commit_action('Cherry-pick', 'cherry_pick')



    def revert(self):
        view = self.view
        captured_path = view.path
        captured_branch = view.snapshot.status.branch if view.snapshot else None
        view._commit_action('Revert', 'revert')



    def _commit_action(self, title, callback):
        view = self.view
        captured_path = view.path
        captured_branch = view.snapshot.status.branch if view.snapshot else None
        commit = view.history.selected_commit()
        if not commit: view._message('Select a commit in History first.', error=True); return
        if len(commit.parents) > 1:
            view._message('Merge commits require a mainline choice; this version supports ordinary commits.', error=True)
            return
        if view._confirm(title + ' commit?', f'{title} {commit.oid[:8]} — {commit.subject}?'):
            self.dispatch(title + ' commit', callback, commit.oid, repository=captured_path, branch=captured_branch)


    def finish_operation(self, abort=False):
        view = self.view
        captured_path = view.path
        captured_branch = view.snapshot.status.branch if view.snapshot else None
        if not view.snapshot: return
        operation = view.snapshot.operation
        if abort and not view._confirm('Abort operation?', f'Abort the current {operation}? Git will attempt to restore its starting state.'):
            return
        self.dispatch(('Abort ' if abort else 'Continue ') + operation, 'finish_operation', operation, abort, repository=captured_path, branch=captured_branch)


    def tag_dialog(self):
        view = self.view
        captured_path = view.path
        captured_branch = view.snapshot.status.branch if view.snapshot else None
        dialog = FormDialog('Create tag', view, 'Leave the message empty for a lightweight tag. Tags are created locally; use the tag context menu to push one.')
        name = dialog.text('Tag name')
        message = dialog.text('Annotation (optional)')
        selected = view.history.selected_commit()
        base = dialog.check('Tag selected history commit' + (f' ({selected.oid[:8]})' if selected else ''))
        base.setEnabled(selected is not None)
        if dialog.submitted():
            value, annotation = name.text(), message.text()
            oid = selected.oid if selected and base.isChecked() else None
            self.dispatch('Create tag', 'create_tag', value, annotation, oid, repository=captured_path, branch=captured_branch)


    def push_tag(self, name):
        view = self.view
        captured_path = view.path
        captured_branch = view.snapshot.status.branch if view.snapshot else None
        dialog = FormDialog('Push tag', view, f'Publish tag {name}.')
        remote = dialog.choice('Remote', view.snapshot.remotes)
        if dialog.submitted() and remote.currentText():
            value = remote.currentText()
            self.dispatch('Push tag', 'push_tag', value, name, repository=captured_path, branch=captured_branch)


    def delete_tag(self, name):
        view = self.view
        captured_path = view.path
        captured_branch = view.snapshot.status.branch if view.snapshot else None
        if view._confirm('Delete local tag?', f'Delete tag {name} locally? Any remote copy is kept.'):
            self.dispatch('Delete tag', 'delete_tag', name, repository=captured_path, branch=captured_branch)


    def reflog_dialog(self):
        view = self.view
        captured_path = view.path
        captured_branch = view.snapshot.status.branch if view.snapshot else None
        path = view.path
        def show(entries):
            if view.path != captured_path or view.closing:
                return
            if not entries:
                view._message('This repository has no HEAD reflog entries.')
                return
            dialog = FormDialog('Recover from reflog', view, 'Create a branch at a previous HEAD position. This preserves the current working tree unless you choose to switch branches. Only the latest 100 HEAD entries are shown.')
            entry = dialog.choice('Reflog entry', [f'{ref} · {oid[:8]} · {message}' for oid, ref, message in entries])
            name = dialog.text('Recovery branch', 'rescue/recovered')
            switch = dialog.check('Switch to recovery branch')
            if dialog.submitted():
                oid, value, checkout = entries[entry.currentIndex()][0], name.text(), switch.isChecked()
                self.dispatch('Create recovery branch', 'create_branch', value, checkout, oid, repository=captured_path, branch=captured_branch)
        view._job('Read reflog', lambda runner: Repository(path, runner).reflog(), show)


    def identity_dialog(self):
        view = self.view
        captured_path = view.path
        captured_branch = view.snapshot.status.branch if view.snapshot else None
        path = view.path
        def show(values):
            if view.path != captured_path or view.closing:
                return
            dialog = FormDialog('Repository commit identity', view, 'Save author identity in this repository’s local Git configuration. Linked worktrees share these settings. Global Git settings are kept.')
            name = dialog.text('Author name', values[0])
            email = dialog.text('Author email', values[1])
            if dialog.submitted():
                author, address = name.text(), email.text()
                self.dispatch('Save repository identity', 'set_identity', author, address, repository=captured_path, branch=captured_branch)
        view._job('Read commit identity', lambda runner: Repository(path, runner).identity(), show)
