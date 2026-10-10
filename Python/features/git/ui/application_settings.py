"""Application Git preferences with feature-owned pages and explicit scope."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from commonUtils.ui import pyside as qt
from .chrome import action_icon
from .dialogs import FormDialog
from ..options import validate_options, validate_account


class GitPreferencesDialog(qt.QDialog):
    def __init__(self, preferences, global_identity, parent):
        super().__init__(parent)
        self.setWindowTitle('Git preferences')
        self.resize(1200, 760)
        self.options = deepcopy(preferences.options)
        self.preferences = preferences
        self.credentials = []
        self.global_identity = global_identity
        self.fields = {}
        layout = qt.QVBoxLayout(self)
        header = qt.QHBoxLayout()
        self.heading = qt.QLabel('General')
        font = qt.QFont(self.font()); font.setPointSizeF(font.pointSizeF() + 3); font.setBold(True)
        self.heading.setFont(font); self.heading.setMinimumWidth(150); header.addWidget(self.heading)
        self.navigation = qt.QToolBar(); self.navigation.setMovable(False)
        self.navigation.setToolButtonStyle(qt.Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.navigation.setIconSize(qt.QSize(24, 24)); header.addWidget(self.navigation, 1); layout.addLayout(header)
        self.navigation_group = qt.QActionGroup(self); self.navigation_group.setExclusive(True)
        self.tabs = qt.QTabWidget(); self.tabs.setIconSize(qt.QSize(24, 24))
        self.tabs.tabBar().hide()
        self.tabs.currentChanged.connect(lambda index: self.heading.setText(self.tabs.tabText(index)))
        layout.addWidget(self.tabs, 1)
        self.general(); self.accounts(); self.commit(); self.diff(); self.git()
        self.unsupported('Mercurial', 'Logistics currently supports Git repositories. Mercurial repositories, extensions and embedded runtimes are not supported.')
        self.actions(); self.update_page(); self.advanced()
        self.error = qt.QLabel(); self.error.setWordWrap(True); layout.addWidget(self.error)
        buttons = qt.QDialogButtonBox(qt.QDialogButtonBox.StandardButton.Ok | qt.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def page(self, title, icon='settings'):
        scroll = qt.QScrollArea(); scroll.setWidgetResizable(True)
        body = qt.QWidget(); box = qt.QVBoxLayout(body); box.setContentsMargins(16, 16, 16, 16); box.setSpacing(10)
        scroll.setWidget(body); index = self.tabs.addTab(scroll, action_icon(icon), title)
        action = self.navigation.addAction(action_icon(icon), title)
        action.setCheckable(True); action.setChecked(index == 0); self.navigation_group.addAction(action)
        action.triggered.connect(lambda checked=False, index=index: self.tabs.setCurrentIndex(index))
        self.tabs.currentChanged.connect(lambda current, index=index, action=action: action.setChecked(current == index))
        return box

    def note(self, box, text):
        label = qt.QLabel(text); label.setTextFormat(qt.Qt.TextFormat.PlainText); label.setWordWrap(True); box.addWidget(label)

    def check(self, box, key, text):
        widget = qt.QCheckBox(text); widget.setChecked(self.options[key]); self.fields[key] = widget; box.addWidget(widget)
        return widget

    def text(self, form, key, title):
        widget = qt.QLineEdit(self.options[key]); self.fields[key] = widget; form.addRow(title, widget); return widget

    def combo(self, form, key, title, values):
        widget = qt.QComboBox(); widget.addItems(values); widget.setCurrentText(self.options[key]); self.fields[key] = widget; form.addRow(title, widget)
        return widget

    def number(self, form, key, title, low, high):
        widget = qt.QSpinBox(); widget.setRange(low, high); widget.setValue(self.options[key]); self.fields[key] = widget; form.addRow(title, widget)
        return widget

    def browse(self, form, key, title, folder=False):
        row = qt.QWidget(); layout = qt.QHBoxLayout(row); layout.setContentsMargins(0, 0, 0, 0)
        edit = qt.QLineEdit(self.options[key]); self.fields[key] = edit; layout.addWidget(edit)
        button = qt.QPushButton('Browse…'); layout.addWidget(button)
        def choose():
            path = qt.QFileDialog.getExistingDirectory(self, title, edit.text()) if folder else qt.QFileDialog.getOpenFileName(self, title, edit.text())[0]
            if path: edit.setText(path)
        button.clicked.connect(choose); form.addRow(title, row); return edit

    def general(self):
        box = self.page('General', 'folder')
        self.modify_global = qt.QCheckBox('Allow Logistics to update global Git author identity'); box.addWidget(self.modify_global)
        form = qt.QFormLayout(); box.addLayout(form)
        self.author = qt.QLineEdit(self.global_identity.get('user.name') or ''); form.addRow('Full name', self.author)
        self.email = qt.QLineEdit(self.global_identity.get('user.email') or ''); form.addRow('Email', self.email)
        self.author.setEnabled(False); self.email.setEnabled(False)
        self.modify_global.toggled.connect(self.author.setEnabled); self.modify_global.toggled.connect(self.email.setEnabled)
        self.browse(form, 'project_folder', 'Project folder', True)
        terminal = self.combo(form, 'terminal', 'Terminal app', ['System default', 'Terminal', 'iTerm'])
        terminal.setEnabled(sys.platform == 'darwin')
        self.check(box, 'restore_windows', 'Restore the last repository on startup')
        self.check(box, 'auto_refresh', 'Refresh automatically when files change')
        self.check(box, 'fetch_updates', 'Fetch origin periodically while this repository is open')
        self.number(form, 'fetch_minutes', 'Fetch interval (minutes)', 1, 1440)
        self.check(box, 'confirm_stage', 'Confirm before staging or unstaging files')
        self.check(box, 'confirm_switch', 'Confirm switching branches when the working copy is clean')
        self.note(box, 'Theme, language and general app updates use Logistics settings. Repositories retain their own author overrides. Background fetch is off by default.')
        box.addStretch()

    def table(self, box, headers):
        table = qt.QTreeWidget(); table.setHeaderLabels(headers); table.setRootIsDecorated(False); box.addWidget(table, 1)
        return table

    def row_buttons(self, box, buttons):
        row = qt.QHBoxLayout()
        for title, callback in buttons:
            button = qt.QPushButton(title); button.clicked.connect(callback); row.addWidget(button)
        row.addStretch(); box.addLayout(row)

    def accounts(self):
        box = self.page('Accounts', 'security')
        self.note(box, 'Tokens are saved in a native secure Git credential helper. Preferences contain account names only. SSH uses your existing keys and agent. Account changes take effect when you click OK.')
        self.account_table = self.table(box, ['Username', 'Provider / host', 'Protocol', 'Default'])
        self.render_accounts()
        self.row_buttons(box, [('Add…', lambda: self.account(False)), ('Edit…', lambda: self.account(True)),
                               ('Remove…', self.remove_account), ('Set Default', self.default_account), ('GitHub browser sign-in…', self.browser_login)])

    def render_accounts(self):
        self.account_table.clear()
        for account in self.options['accounts']:
            qt.QTreeWidgetItem(self.account_table, [account['username'], account['host'], account['protocol'].upper(), 'Default' if account.get('default') else ''])

    def account(self, edit):
        index = self.account_table.indexOfTopLevelItem(self.account_table.currentItem())
        if edit and index < 0: return
        old = self.options['accounts'][index] if edit else {}
        dialog = FormDialog('Edit account' if edit else 'Add account', self, 'Leave the token empty to use an existing credential. Tokens never go into Git URLs, logs or preferences.')
        host = dialog.text('Host', old.get('host', 'github.com')); user = dialog.text('Username', old.get('username', ''))
        protocol = dialog.choice('Protocol', ['https', 'ssh']); protocol.setCurrentText(old.get('protocol', 'https'))
        helper = dialog.choice('HTTPS authentication', ['Existing Git helper', 'Git Credential Manager (browser sign-in)'])
        if old.get('helper') == 'manager': helper.setCurrentIndex(1)
        token = dialog.text('Personal access token'); token.setEchoMode(qt.QLineEdit.EchoMode.Password)
        if not dialog.submitted(): token.clear(); return
        account = {'host': host.text().strip().lower(), 'username': user.text().strip(), 'protocol': protocol.currentText(), 'default': old.get('default', not self.options['accounts'])}
        if old.get('helper'): account['helper'] = old['helper']
        if helper.currentIndex() == 1: account['helper'] = 'manager'
        try:
            validate_account(account)
            if any(a['host'] == account['host'] and a['username'] == account['username'] and a['protocol'] == account['protocol'] for i, a in enumerate(self.options['accounts']) if not edit or i != index):
                raise ValueError('This account is already listed.')
            if token.text() and account['protocol'] != 'https': raise ValueError('SSH accounts use keys rather than tokens.')
            if token.text(): self.credentials.append((account, token.text(), False))
            if edit: self.options['accounts'][index] = account
            else: self.options['accounts'].append(account)
            self.render_accounts()
        except ValueError as error: qt.QMessageBox.warning(self, 'Account', str(error))
        finally: token.clear()

    def remove_account(self):
        index = self.account_table.indexOfTopLevelItem(self.account_table.currentItem())
        if index < 0: return
        account = self.options['accounts'][index]
        if qt.QMessageBox.question(self, 'Remove account?', 'Remove this account and erase its saved HTTPS credential when you click OK?') != qt.QMessageBox.StandardButton.Yes: return
        self.credentials = [entry for entry in self.credentials if entry[0] != account]
        self.credentials.append((account, None, True)); self.options['accounts'].pop(index); self.render_accounts()

    def default_account(self):
        index = self.account_table.indexOfTopLevelItem(self.account_table.currentItem())
        if index < 0: return
        selected = self.options['accounts'][index]
        for i, account in enumerate(self.options['accounts']):
            if account['host'] == selected['host']: account['default'] = i == index
        self.render_accounts()

    def browser_login(self):
        self.note_browser = 'GitHub sign-in runs in your terminal through Git Credential Manager. After signing in, add the username here and choose it as default.'
        from ..accounts import browser_login_command
        from commonUtils.integrations.wrappers.cmdShellWrapper.terminal import exec_cmd_new_window
        try:
            if exec_cmd_new_window(browser_login_command(self.preferences.executable), str(Path.home())) is False:
                raise OSError('A terminal could not be opened. Install Git Credential Manager to use browser sign-in.')
        except OSError as error: qt.QMessageBox.warning(self, 'Sign-in', str(error))
        else: self.error.setText(self.note_browser)

    def commit(self):
        box = self.page('Commit', 'template')
        self.check(box, 'select_all_commit', 'Select all pending files when opening Commit')
        self.note(box, 'Selection does not stage files. Commit always uses the index.')
        self.check(box, 'push_after_commit', 'Default to pushing to origin after committing')
        self.check(box, 'fixed_commit_font', 'Use a fixed-width font for commit messages')
        form = qt.QFormLayout(); box.addLayout(form)
        self.number(form, 'commit_guide', 'Message column guide', 20, 200)
        self.note(box, 'Default message template. An explicit repository template or “None” overrides it. Existing drafts are kept.')
        self.template = qt.QPlainTextEdit(self.options['commit_template']); box.addWidget(self.template, 1)
        def import_template():
            path = qt.QFileDialog.getOpenFileName(self, 'Import text template')[0]
            if path:
                try:
                    if Path(path).stat().st_size > 65536: raise ValueError('Template must be smaller than 64 KiB.')
                    self.template.setPlainText(Path(path).read_text(encoding='utf-8'))
                except (OSError, ValueError) as error: self.error.setText(str(error))
        self.row_buttons(box, [('Import…', import_template)])

    def diff(self):
        box = self.page('Diff', 'stash'); form = qt.QFormLayout(); box.addLayout(form)
        self.font_button = qt.QPushButton(self.options['diff_font'] or 'System monospace font')
        def choose_font():
            font = qt.QFont(); font.fromString(self.options['diff_font'])
            accepted, font = qt.QFontDialog.getFont(font, self)
            if accepted: self.options['diff_font'] = font.toString(); self.font_button.setText(font.toString())
        self.font_button.clicked.connect(choose_font); form.addRow('Diff font', self.font_button)
        self.number(form, 'diff_limit_kb', 'Text preview limit (KiB)', 16, 16384)
        self.text(form, 'diff_ignore_patterns', 'Skip preview patterns (comma separated)')
        self.check(box, 'wrap_diff', 'Wrap diff lines by default')
        color_row = qt.QHBoxLayout()
        for kind, label in [('add', 'Added'), ('remove', 'Removed')]:
            for position, suffix in [(0, 'text'), (1, 'background')]:
                button = qt.QPushButton(f'{label}: {suffix} color…')
                button.clicked.connect(lambda checked=False, kind=kind, position=position: self.choose_color(kind, position))
                color_row.addWidget(button)
        box.addLayout(color_row)
        self.row_buttons(box, [('Reset font and colors', self.reset_diff)])
        self.text(form, 'external_diff', 'External diff tool (Git tool name)')
        self.text(form, 'external_merge', 'External merge tool (Git tool name)')
        self.note(box, 'Tools use their existing Git difftool/mergetool configuration. Binary files have no internal text preview. Tool setup and arbitrary shell arguments are managed in Git configuration.')
        box.addStretch()

    def choose_color(self, kind, position):
        from commonUtils.ui.code_editor.diff_bands import diff_colors
        colors = self.options['diff_colors'].setdefault(kind, list(diff_colors(self.palette(), kind)))
        color = qt.QColorDialog.getColor(qt.QColor(colors[position]), self)
        if color.isValid(): colors[position] = color.name()

    def reset_diff(self):
        self.options['diff_font'] = ''; self.options['diff_colors'] = {}; self.font_button.setText('System monospace font')

    def git(self):
        box = self.page('Git', 'branch'); form = qt.QFormLayout(); box.addLayout(form)
        self.executable = qt.QLineEdit(self.preferences.executable); form.addRow('Git executable', self.executable)
        self.browse(form, 'global_ignore', 'Ignore list for Logistics Git commands')
        self.combo(form, 'pull_strategy', 'Default pull strategy', ['ff-only', 'merge', 'rebase'])
        self.check(box, 'stage_double_click', 'Stage / unstage files on double click')
        self.check(box, 'recursive_submodules', 'Perform submodule updates recursively')
        self.check(box, 'check_submodules', 'Check submodules before commit and push')
        self.check(box, 'push_tags', 'Push tags with the selected branch')
        self.check(box, 'ssl_verify', 'Verify HTTPS certificates')
        self.check(box, 'no_ff', 'Always create a commit when merging')
        self.check(box, 'author_date', 'Display author date instead of commit date')
        self.note(box, 'Logistics uses system Git (2.40+). Embedded Git, git-flow and LFS runtimes are not bundled. Push always targets the selected branch; it does not use push.default=matching.')
        self.row_buttons(box, [('Use system Git', lambda: self.executable.setText('git'))]); box.addStretch()

    def unsupported(self, title, text):
        box = self.page(title); self.note(box, text); box.addStretch()

    def actions(self):
        box = self.page('Custom Actions', 'merge')
        self.note(box, 'Actions run without a shell in the active repository. Parameters are a JSON list. Each argument supports {repo}, {file} and {commit}. A shortcut is optional.')
        self.action_table = self.table(box, ['Menu caption', 'Program', 'Arguments', 'Shortcut']); self.render_actions()
        self.row_buttons(box, [('Add…', lambda: self.action(False)), ('Edit…', lambda: self.action(True)), ('Remove', self.remove_action),
                               ('↑', lambda: self.move_action(-1)), ('↓', lambda: self.move_action(1))])

    def render_actions(self):
        self.action_table.clear()
        for action in self.options['custom_actions']:
            qt.QTreeWidgetItem(self.action_table, [action['caption'], action['program'], json.dumps(action['arguments']), action['shortcut']])

    def action(self, edit):
        index = self.action_table.indexOfTopLevelItem(self.action_table.currentItem())
        if edit and index < 0: return
        old = self.options['custom_actions'][index] if edit else {}
        dialog = FormDialog('Custom action', self)
        caption = dialog.text('Menu caption', old.get('caption', '')); program = dialog.text('Program', old.get('program', ''))
        arguments = dialog.text('Arguments (JSON list)', json.dumps(old.get('arguments', [])))
        shortcut = dialog.text('Shortcut', old.get('shortcut', ''))
        if not dialog.submitted(): return
        try:
            action = {'caption': caption.text(), 'program': program.text(), 'arguments': json.loads(arguments.text()), 'shortcut': shortcut.text()}
            options = deepcopy(self.options)
            if edit: options['custom_actions'][index] = action
            else: options['custom_actions'].append(action)
            self.options = validate_options(options); self.render_actions()
        except (ValueError, TypeError) as error: self.error.setText(str(error))

    def remove_action(self):
        index = self.action_table.indexOfTopLevelItem(self.action_table.currentItem())
        if index >= 0: self.options['custom_actions'].pop(index); self.render_actions()

    def move_action(self, step):
        index = self.action_table.indexOfTopLevelItem(self.action_table.currentItem()); target = index + step
        if index >= 0 and 0 <= target < len(self.options['custom_actions']):
            actions = self.options['custom_actions']; actions[index], actions[target] = actions[target], actions[index]
            self.render_actions(); self.action_table.setCurrentItem(self.action_table.topLevelItem(target))

    def update_page(self):
        box = self.page('Update', 'fetch')
        self.note(box, 'Git ships as part of Logistics. Releases and release notes are published together; updating this feature separately is not supported.')
        def releases(): qt.QDesktopServices.openUrl(qt.QUrl('https://github.com/ispaure/logistics/releases'))
        self.row_buttons(box, [('Check releases', releases), ('Show release notes', releases)]); box.addStretch()

    def advanced(self):
        box = self.page('Advanced'); form = qt.QFormLayout(); box.addLayout(form)
        self.check(box, 'keep_backups', 'Keep file backups before discarding changes')
        self.check(box, 'full_output', 'Always show the operation log')
        self.check(box, 'allow_force_push', 'Allow force push with lease')
        self.check(box, 'debug_menu', 'Show Git diagnostics in the More menu')
        self.browse(form, 'gpg_program', 'GPG program')
        self.note(box, 'Backups are stored in the repository Git metadata under logistics-backups. Force push still requires confirmation. Git hooks and custom actions manage their own side effects.')
        self.usernames = self.table(box, ['Host', 'Default HTTPS username'])
        for host, user in self.options['default_usernames'].items(): qt.QTreeWidgetItem(self.usernames, [host, user])
        def add_username():
            dialog = FormDialog('Default username', self); host = dialog.text('Host'); user = dialog.text('Username')
            if dialog.submitted():
                try: validate_account({'host': host.text(), 'username': user.text(), 'protocol': 'https'})
                except ValueError as error: self.error.setText(str(error)); return
                for i in range(self.usernames.topLevelItemCount()):
                    item = self.usernames.topLevelItem(i)
                    if item.text(0) == host.text(): item.setText(1, user.text()); return
                qt.QTreeWidgetItem(self.usernames, [host.text(), user.text()])
        def remove_username():
            index = self.usernames.indexOfTopLevelItem(self.usernames.currentItem())
            if index >= 0: self.usernames.takeTopLevelItem(index)
        self.row_buttons(box, [('Add / Edit…', add_username), ('Remove', remove_username)])

    def accept(self):
        try:
            for key, widget in self.fields.items():
                self.options[key] = widget.isChecked() if isinstance(widget, qt.QCheckBox) else widget.value() if isinstance(widget, qt.QSpinBox) else widget.currentText() if isinstance(widget, qt.QComboBox) else widget.text()
            self.options['commit_template'] = self.template.toPlainText()
            if len(self.options['commit_template'].encode()) > 65536: raise ValueError('Template must be smaller than 64 KiB.')
            self.options['default_usernames'] = {self.usernames.topLevelItem(i).text(0): self.usernames.topLevelItem(i).text(1) for i in range(self.usernames.topLevelItemCount())}
            self.options = validate_options(self.options)
            if not self.executable.text().strip(): raise ValueError('Choose a Git executable.')
            if self.modify_global.isChecked() and any(not text.strip() or any(ord(c) < 32 for c in text) for text in (self.author.text(), self.email.text())):
                raise ValueError('Enter an author name and email without control characters.')
        except (ValueError, TypeError) as error: self.error.setText(str(error)); return
        super().accept()
