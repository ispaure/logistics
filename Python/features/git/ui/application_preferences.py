"""Runtime application of feature preferences across retained Git panes."""
from copy import deepcopy
from fnmatch import fnmatch
from pathlib import Path
from commonUtils.ui import pyside as qt
from .application_settings import GitPreferencesDialog
from ..runner import GitError


class ApplicationPreferences:
    def application_settings_dialog(self):
        if self.busy: return
        def show(identity):
            dialog = GitPreferencesDialog(self.preferences, identity, self)
            if dialog.exec() != qt.QDialog.DialogCode.Accepted: return
            options = deepcopy(dialog.options); executable = dialog.executable.text().strip()
            credentials = list(dialog.credentials)
            dialog.credentials.clear()
            requested_identity = {'user.name': dialog.author.text().strip(), 'user.email': dialog.email.text().strip()} if dialog.modify_global.isChecked() else None
            def save(runner):
                from ..accounts import change_credential, secure_helper
                from ..runner import GitRunner
                GitRunner(executable, cancel=runner.cancel).version()
                runner.executable = executable
                if requested_identity:
                    for key in requested_identity:
                        current = runner.run(['config', '--global', '--get', key], check=False).stdout.decode().strip() or None
                        if current != identity[key]: raise GitError('Global identity changed while preferences were open. Reopen preferences.')
                try:
                    for account, token, erase in credentials:
                        if account['protocol'] == 'https':
                            helper = account.get('helper') or secure_helper(runner)
                            account['helper'] = helper
                            change_credential(runner, account, token, erase=erase)
                            for saved in options['accounts']:
                                if (saved['host'], saved['username'], saved['protocol']) == (account['host'], account['username'], account['protocol']): saved['helper'] = helper
                finally: credentials.clear()
                if requested_identity:
                    for key, value in requested_identity.items(): runner.run(['config', '--global', key, value])
                return options
            def applied(saved):
                old_options, old_executable = self.preferences.options, self.preferences.executable
                self.preferences.options, self.preferences.executable = saved, executable
                try: self.preferences.save()
                except OSError:
                    self.preferences.options, self.preferences.executable = old_options, old_executable
                    raise
                for view in list(self.preferences.views):
                    view.apply_preferences(); view.refresh()
            self._job('Save Git preferences', save, applied)
        self._job('Read global Git identity', lambda runner: {
            key: runner.run(['config', '--global', '--get', key], check=False).stdout.decode().strip() or None
            for key in ('user.name', 'user.email')}, show)

    def init_preferences(self):
        self.preferences.views.add(self)
        self._message_font = qt.QFont(self.changes.message.font())
        self._diff_font = qt.QFont(self.preview.editor.font())
        self.custom_menu = self.more_menu.addMenu('Custom Actions')
        self.more_menu.addAction('Git preferences…', self.application_settings_dialog)
        self.more_menu.addAction('External diff for selected file', lambda: self.external_tool(False))
        self.more_menu.addAction('External merge for selected conflict', lambda: self.external_tool(True))
        self.repository_menu.addSeparator(); self.repository_menu.addAction('Git preferences…', self.application_settings_dialog)
        self.debug_action = self.more_menu.addAction('Git diagnostics', self.git_diagnostics)
        self.watch = qt.QFileSystemWatcher(self)
        self.watch.fileChanged.connect(self.files_changed); self.watch.directoryChanged.connect(self.files_changed)
        self.file_timer = qt.QTimer(self); self.file_timer.setSingleShot(True); self.file_timer.setInterval(500)
        self.file_timer.timeout.connect(self.refresh)
        self.fetch_timer = qt.QTimer(self); self.fetch_timer.timeout.connect(self.background_fetch)
        self.apply_preferences()

    def apply_preferences(self):
        options = self.preferences.options
        from commonUtils.ui.code_editor.widget import monospace_font
        self.changes.message.setFont(monospace_font() if options['fixed_commit_font'] else self._message_font)
        self.changes.message.column_guide = options['commit_guide'] if options['fixed_commit_font'] else 0
        self.changes.message.viewport().update()
        self.changes.stage_on_double_click = options['stage_double_click']
        if self.changes.default_push != options['push_after_commit'] and self.changes.push_immediately.isEnabled():
            self.changes.push_immediately.setChecked(options['push_after_commit'])
        self.changes.default_push = options['push_after_commit']
        font = qt.QFont(self._diff_font)
        if options['diff_font']: font.fromString(options['diff_font'])
        self.preview.editor.setFont(font)
        self.preview.editor.diff_color_overrides = options['diff_colors']
        self.preview.diff_color_overrides = options['diff_colors']
        self.preview.wrap.setChecked(options['wrap_diff'])
        self.preview._render_diff()
        self.preview.highlighter.rehighlight()
        self.log_toggle.setChecked(options['full_output'])
        self.debug_action.setVisible(options['debug_menu'])
        self.custom_menu.clear()
        for entry in options['custom_actions']:
            action = self.custom_menu.addAction(entry['caption'], lambda checked=False, entry=deepcopy(entry): self.run_custom_action(entry))
            if entry['shortcut']:
                action.setShortcut(qt.QKeySequence(entry['shortcut'])); action.setShortcutContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
                self.addAction(action)
        self.custom_menu.setEnabled(bool(options['custom_actions']))
        self.fetch_timer.stop()
        if options['fetch_updates']: self.fetch_timer.start(options['fetch_minutes'] * 60000)
        self.update_watch()

    def update_watch(self):
        watched = self.watch.files() + self.watch.directories()
        if watched: self.watch.removePaths(watched)
        if not self.path or not self.preferences.options['auto_refresh'] or not self.snapshot: return
        paths = {str(self.path)}
        git = self.path / '.git'
        if git.is_dir(): paths.add(str(git))
        for change in self.snapshot.status.changes:
            file = self.path / change.path
            if file.is_file() and not file.is_symlink(): paths.add(str(file))
            if file.parent.is_dir(): paths.add(str(file.parent))
        # Watch tracked files too, so the first edit to a clean file refreshes status.
        for file in getattr(self.snapshot, 'tracked_paths', ()):
            path = self.path / file
            if path.is_file() and not path.is_symlink(): paths.add(str(path))
            if path.parent.is_dir(): paths.add(str(path.parent))
        self.watch.addPaths(sorted(paths)[:2000])

    def files_changed(self, path):
        if not self.closing and self.preferences.options['auto_refresh']: self.file_timer.start()

    def background_fetch(self):
        if not self.closing and not self.busy and self.snapshot and 'origin' in self.snapshot.remotes:
            self._operation('Background fetch origin', lambda repo: repo.run(['fetch', '--prune', '--progress', 'origin'], timeout=1800))

    def skip_preview(self, path):
        patterns = [pattern.strip() for pattern in self.preferences.options['diff_ignore_patterns'].split(',') if pattern.strip()]
        if any(fnmatch(path, pattern) or fnmatch(Path(path).name, pattern) for pattern in patterns):
            self.preview.hide_file_actions()
            self.preview.show_text(path, 'Preview skipped by Git diff preferences. File actions still affect the complete file.')
            return True
        return False

    def stage_files(self, paths, unstage=False):
        if self.preferences.options['confirm_stage'] and not self._confirm('Unstage files?' if unstage else 'Stage files?', '\n'.join(paths)): return
        self._operation('Unstage files' if unstage else 'Stage files', lambda repo: repo.unstage(paths) if unstage else repo.stage(paths))

    def run_custom_action(self, entry):
        if self.busy or not self.path: return
        change = self.changes.selected()
        path = change[0].path if change else ''
        commit = self.history.selected_commit()
        values = {'{repo}': str(self.path), '{file}': path, '{commit}': commit.oid if commit else ''}
        args = []
        for argument in entry['arguments']:
            for placeholder, value in values.items():
                if placeholder in argument and not value:
                    self._message(f'Select a file or commit for {placeholder}.', error=True); return
                argument = argument.replace(placeholder, value)
            args.append(argument)
        self._operation(entry['caption'], lambda repo: repo.runner.run(args, external=entry['program'], cwd=repo.path, timeout=1800))

    def git_diagnostics(self):
        self._job('Git diagnostics', lambda runner: runner.version(), lambda version:
                  self._append_log(f'{version}\nExecutable: {self.preferences.executable}\nPreferences: {self.preferences.path}\nRepository: {self.path}\n'))

    def external_tool(self, merge):
        changes = self.changes.selected()
        if len(changes) != 1:
            self._message('Select one file in File status.', error=True); return
        change = changes[0]
        tool = self.preferences.options['external_merge' if merge else 'external_diff']
        if not tool:
            self._message('Choose a Git-configured external tool in Git preferences → Diff.', error=True); return
        if merge and not change.conflict:
            self._message('Select a conflicted file to merge.', error=True); return
        if not merge and change.index == '?':
            self._message('Stage the new file before launching an external diff.', error=True); return
        args = ['mergetool' if merge else 'difftool', '--no-prompt', '--tool=' + tool]
        if not merge and change.staged and change in self.changes.selected(True): args.append('--cached')
        args += ['--', change.path]
        self._operation('External merge' if merge else 'External diff', lambda repo: repo.run(args, timeout=1800))
