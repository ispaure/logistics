"""History/search/preview presentation using the repository view's sequential jobs.

The view retains command and worker ownership. This controller owns history limits,
reload selection and deferred search/focus state; it never starts another worker.
"""
from commonUtils.ui import pyside as qt
from ..repository import Repository


class RepositoryHistory:
    def __init__(self, view):
        self.view = view
        self.limit = 200
        self.reload = None
        self.search_pending = False
        self.focus_pending = False
        self.comparison_selection = None

    def preview_change(self, change, staged):
        view = self.view
        if view.busy or not view.path: return
        if view.skip_preview(change.path): return
        self.comparison_selection = (change, staged)
        view.preview.compare_button.setVisible(not change.conflict and change.submodule == "N...")
        self.reload = lambda: view.preview_change(change, staged)
        path = view.path
        ignore_whitespace = view.preview.ignore_whitespace.isChecked()
        def read(runner):
            repo = Repository(path, runner)
            return repo.untracked_preview(change.path) if change.index == '?' else repo.diff(
                change.path, staged=staged, ignore_whitespace=ignore_whitespace)
        view.preview.set_file_actions(staged, change.index != '?' and not change.conflict)
        def show(text):
            title = ('Staged: ' if staged else 'Working tree: ') + change.path
            text = text or ('No differences with whitespace ignored.' if ignore_whitespace else 'No textual differences.')
            if change.index == '?':
                view.preview.show_text(title, text)
            else:
                allowed = not (ignore_whitespace or change.conflict or change.original_path or change.submodule != 'N...'
                               or any(line.startswith(('old mode ', 'new mode ', 'rename ', 'copy ')) for line in text.splitlines()))
                context = {'root': str(path), 'path': change.path, 'staged': staged, 'patch': text,
                           'allowed': allowed, 'reason': '' if allowed else
                           'Use the complete file action, or turn off Ignore whitespace for hunk actions.'}
                view.preview.show_diff(title, text, hunk_context=context)
        view._job('Read file changes', read, show)


    def compare_change(self):
        view = self.view
        if view.busy or not view.path or not getattr(view, '_comparison_selection', None):
            return
        from commonUtils.ui.code_editor.diff import DiffDialog, compare_text
        change, staged = self.comparison_selection
        path = view.path
        names = ('HEAD', 'Index') if staged else ('Index', 'Working file')
        def read(runner):
            left, right = Repository(path, runner).comparison_inputs(change.path, staged=staged)
            return compare_text(left, right, *names)
        def show(model):
            if view.path == path and not view.closing:
                dialog = DiffDialog(model, view, left_name=names[0], right_name=names[1], path=path/change.path)
                from services.editors.ui.fonts import bind_code_views
                bind_code_views(dialog)
                dialog.show()
        view._job('Compare file versions', read, show)


    def _reload_preview(self, *args):
        view = self.view
        reload = getattr(view, '_preview_reload', None)
        if reload and not view.busy: reload()


    def preview_commit(self, commit, panel=None):
        view = self.view
        if view.busy or not view.path or commit is None: return
        panel = panel or view.history
        self.reload = None
        path = view.path
        full_tree = bool(panel.file_mode.currentIndex())
        def read(runner):
            repo = Repository(path, runner)
            return repo.commit_metadata(commit.oid), (repo.tree(commit.oid) if full_tree else repo.commit_files(commit.oid))
        def show(result):
            details, entries = result
            view.preview.show_text(commit.oid + ' · ' + commit.subject, 'Select a file to review its changes.')
            panel.set_tree(entries)
            panel.set_metadata(details)
            view.preview.hide_file_actions()
            panel.select_first_file()
        view._job('Read commit', read, show)


    def focus_parent(self, oid):
        view = self.view
        if view.busy or not view.path: return
        view.history.search.clear()
        view.history.branch_filter.setCurrentIndex(0)
        if view.history.select_ref(oid): return
        path = view.path
        def show(commits):
            self.limit = 5000
            view.history.set_commits(commits, False)
            if not view.history.select_ref(oid):
                view.status.setText('Parent is outside the 5,000-commit history limit.')
        view._job('Load parent history', lambda runner: Repository(path, runner).history(5000), show)


    def preview_blob(self, entry):
        view = self.view
        if view.skip_preview(entry.path): return
        if entry.kind == 'working':
            change = next((change for change in view.snapshot.status.changes if change.path == entry.path), None)
            if change is not None: view.preview_working_file(change)
            return
        if view.busy or not view.path: return
        self.reload = lambda: view.preview_blob(entry)
        if entry.kind == 'change':
            path = view.path
            ignore_whitespace = view.preview.ignore_whitespace.isChecked()
            view._job('Read commit file diff', lambda runner: Repository(path, runner).commit_file_diff(
                entry.oid, entry.path, ignore_whitespace=ignore_whitespace),
                lambda text: view.preview.show_diff(entry.path,
                    text or ('No differences with whitespace ignored.' if ignore_whitespace else 'No textual differences.')))
            return
        if entry.kind == 'commit':
            view.preview.show_text(entry.path, f'Submodule commit: {entry.oid}\nOpen its repository to browse its files.')
            return
        path = view.path
        view._job('Read historical file', lambda runner: Repository(path, runner).blob(entry.oid),
                  lambda text: view.preview.show_text(entry.path + ' · ' + entry.oid[:8], text))


    def _view_changed(self, index):
        view = self.view
        target = (view.change_preview_layout, view.history_preview_layout, view.search_preview_layout)[index]
        target.addWidget(view.preview)
        view.preview.hide_file_actions()
        view._select_navigation(index)
        if index == 2:
            if view.search_results.stale:
                view.search_history()
            elif view.search_results.selected_commit():
                view.preview_commit(view.search_results.selected_commit(), view.search_results)
        elif index == 1:
            if view.history.working_copy_is_selected():
                view.preview_working_copy()
            elif view.history.selected_commit() is None and view.history.table.topLevelItemCount():
                for i in range(view.history.table.topLevelItemCount()):
                    item = view.history.table.topLevelItem(i)
                    if item.data(1, qt.Qt.ItemDataRole.UserRole):
                        view.history.table.setCurrentItem(item)
                        break
            elif view.history.selected_commit(): view.preview_commit(view.history.selected_commit())
        else:
            for tree in (view.changes.staged_files, view.changes.unstaged_files):
                item=tree.currentItem()
                if item:
                    view.preview_change(*item.data(0,qt.Qt.ItemDataRole.UserRole))
                    break
            else:
                self.reload = None
                view.preview.show_text('Select a changed file', '')


    def preview_working_copy(self):
        view = self.view
        if not view.snapshot: return
        from ..models import TreeEntry
        changes = view.snapshot.status.changes
        self.reload = None
        view.history.set_tree([TreeEntry(change.index + change.worktree, 'working', '', change.path)
                               for change in changes])
        view.history.metadata.setPlainText(f'Uncommitted changes\n{len(changes)} changed files in {view.path}')
        view.preview.show_text('Uncommitted changes', 'Select a file to review its changes.')
        view.preview.hide_file_actions()
        view.history.select_first_file()


    def preview_working_file(self, change):
        view = self.view
        if view.busy or not view.path: return
        path = view.path
        plain = change.index == '?' or view.snapshot.status.oid in ('', '(initial)')
        ignore = view.preview.ignore_whitespace.isChecked()
        self.reload = lambda: view.preview_working_file(change)
        view.preview.hide_file_actions()
        def read(runner):
            repo = Repository(path, runner)
            return repo.untracked_preview(change.path) if plain else repo.diff(
                change.path, against_head=True, ignore_whitespace=ignore)
        display = view.preview.show_text if plain else view.preview.show_diff
        view._job('Read uncommitted file', read, lambda text: display('Uncommitted: ' + change.path,
                  text or 'No textual differences.'))


    def search_history(self):
        view = self.view
        panel = view.search_results
        if not view.path or view.closing: return
        panel.timer.stop()
        if view.views.currentIndex() != 2:
            panel.stale = True
            return
        if view.busy:
            self.search_pending = True
            return
        self.search_pending = False
        panel.stale = False
        query, mode, since, until = panel.query()
        token = panel.query(), panel.limit
        path = view.path
        def show(commits):
            if view.path != path or token != (panel.query(), panel.limit):
                self.search_pending = True
                return
            panel.set_commits(commits[:panel.limit], len(commits) > panel.limit and panel.limit < 5000)
            with qt.QSignalBlocker(panel.table): panel.table.setCurrentItem(None)
            panel.tree.clear()
            panel.metadata.clear()
            if view.views.currentIndex() == 2:
                view.preview.show_text('Search results', 'Select a commit to review its files.')
                panel.select_ref(commits[0].oid) if commits else None
        view._job('Search repository history', lambda runner: Repository(path, runner).search_history(
            query, mode, since, until, panel.limit), show)


    def _search_parent(self, oid):
        view = self.view
        view.search_results.mode.setCurrentText('Commit SHA')
        view.search_results.search.setText(oid)


    def load_more_search(self):
        view = self.view
        view.search_results.limit = min(5000, view.search_results.limit + 200)
        view.search_history()


    def load_more(self):
        view = self.view
        self.limit = min(5000, self.limit + 200)
        view.refresh()


    def show_ref_commit(self, ref):
        view = self.view
        # Tags can point to annotated tag objects: resolve to a commit first.
        self.reload = None
        path = view.path
        full_tree = bool(view.history.file_mode.currentIndex())
        def read(runner):
            repo = Repository(path, runner)
            oid = repo.run(['rev-parse', '--verify', ref.name + '^{commit}']).stdout.decode('ascii').strip()
            return oid, repo.commit_metadata(oid), (repo.tree(oid) if full_tree else repo.commit_files(oid))
        def show(result):
            oid, details, entries = result
            view.history.search.clear()
            view.history.branch_filter.setCurrentIndex(0)
            with qt.QSignalBlocker(view.history.table):
                view.history.table.setCurrentItem(None)
                for index in range(view.history.table.topLevelItemCount()):
                    item = view.history.table.topLevelItem(index)
                    commit = item.data(1, qt.Qt.ItemDataRole.UserRole)
                    if commit and commit.oid == oid:
                        view.history.table.setCurrentItem(item)
                        break
            view.preview.show_text(ref.name, 'Select a file to review its changes.')
            view.history.set_tree(entries)
            view.history.set_metadata(details)
            view.preview.hide_file_actions()
            with qt.QSignalBlocker(view.views): view.views.setCurrentIndex(1)
            view.history_preview_layout.addWidget(view.preview)
            view._select_navigation(1)
            view.history.select_first_file()
        view._job('Read reference commit', read, show)


    def compare_to_head(self):
        view = self.view
        selected = view.history.selected_commit()
        if not selected or not view.snapshot:
            view._message('Select a commit in History first.', error=True)
            return
        first, second, path = selected.oid, view.snapshot.status.oid, view.path
        view.preview.hide_file_actions()
        self.reload = view.compare_to_head
        ignore_whitespace = view.preview.ignore_whitespace.isChecked()
        view._job('Compare revisions', lambda runner: Repository(path, runner).compare(
            first, second, ignore_whitespace=ignore_whitespace),
            lambda text: view.preview.show_diff(f'{first[:8]} → HEAD {second[:8]}', text or 'No differences.'))


