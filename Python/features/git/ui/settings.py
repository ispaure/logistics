"""Repository-scoped settings UI; writes use the existing serialized Git worker."""
from commonUtils.ui import pyside as qt
from .chrome import action_icon
from .dialogs import FormDialog


class RepositorySettingsDialog(qt.QDialog):
    def __init__(self, settings, parent):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle('Repository settings')
        self.resize(740, 560)
        layout = qt.QVBoxLayout(self)
        root = qt.QLabel(settings['root'])
        root.setTextFormat(qt.Qt.TextFormat.PlainText)
        root.setWordWrap(True)
        layout.addWidget(root)
        note = qt.QLabel('Changes apply to this repository. Linked worktrees share local Git settings; global settings are kept.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.tabs = qt.QTabWidget()
        self.tabs.setIconSize(qt.QSize(24, 24))
        layout.addWidget(self.tabs, 1)
        self._template()
        self._remotes()
        self._security()
        self._advanced(parent)
        buttons = qt.QDialogButtonBox(qt.QDialogButtonBox.StandardButton.Ok | qt.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _tab(self, title, icon):
        page = qt.QWidget()
        layout = qt.QVBoxLayout(page)
        self.tabs.addTab(page, action_icon(icon), title)
        return layout

    def _template(self):
        layout = self._tab('Commit Template', 'template')
        label = qt.QLabel('Start an empty commit message with a reusable text template. Existing drafts are kept.')
        label.setWordWrap(True)
        layout.addWidget(label)
        if self.settings['template_warning']:
            warning = qt.QLabel(self.settings['template_warning'])
            warning.setWordWrap(True)
            layout.addWidget(warning)
        self.template_mode = qt.QComboBox()
        self.template_mode.addItems(['Inherit Git settings', 'None for this repository', 'Custom for this repository'])
        current = self.settings['local']['commit.template']
        self.template_mode.setCurrentIndex(0 if current is None else 2 if current else 1)
        self._original_template_mode = self.template_mode.currentIndex()
        layout.addWidget(self.template_mode)
        self.template = qt.QPlainTextEdit(self.settings['template_text'])
        self.template.setAccessibleName('Commit template text')
        layout.addWidget(self.template, 1)
        self.template_mode.currentIndexChanged.connect(lambda index: self.template.setReadOnly(index != 2))
        self.template.setReadOnly(self.template_mode.currentIndex() != 2)

    def _remotes(self):
        layout = self._tab('Remotes', 'remote')
        self.remotes = qt.QTreeWidget()
        self.remotes.setHeaderLabels(['Name', 'URL or local path'])
        self.remotes.setRootIsDecorated(False)
        self.remotes.setAccessibleName('Repository remotes')
        for name, url in self.settings['remotes'].items():
            qt.QTreeWidgetItem(self.remotes, [name, url])
        layout.addWidget(self.remotes, 1)
        row = qt.QHBoxLayout()
        for label, callback in [('Add…', lambda: self._remote(False)), ('Edit…', lambda: self._remote(True)), ('Remove', self._remove_remote)]:
            button = qt.QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        layout.addWidget(qt.QLabel('Remote changes are saved when you click OK. Removing a remote keeps the remote repository.'))

    def _remote(self, edit):
        item = self.remotes.currentItem() if edit else None
        if edit and item is None: return
        dialog = FormDialog('Edit remote' if edit else 'Add remote', self)
        name = dialog.text('Name', item.text(0) if item else '')
        name.setReadOnly(edit)
        url = dialog.text('URL or local path', item.text(1) if item else '')
        if dialog.submitted():
            key, value = name.text().strip(), url.text().strip()
            from ..repository import argument, remote_url
            from ..runner import GitError
            try:
                argument(key, 'Remote name'); remote_url(value)
                if not edit and any(self.remotes.topLevelItem(i).text(0) == key for i in range(self.remotes.topLevelItemCount())):
                    raise GitError('A remote with that name already exists.')
            except GitError as exc:
                qt.QMessageBox.warning(self, 'Remote', str(exc))
                return
            if item: item.setText(1, value)
            else: qt.QTreeWidgetItem(self.remotes, [key, value])

    def _remove_remote(self):
        item = self.remotes.currentItem()
        if item:
            self.remotes.takeTopLevelItem(self.remotes.indexOfTopLevelItem(item))

    def _security(self):
        layout = self._tab('Security', 'security')
        form = qt.QFormLayout()
        layout.addLayout(form)
        effective = self.settings['effective']
        self.signing = qt.QComboBox()
        self.signing.addItems(['Inherit Git settings', 'Sign commits', 'Do not sign commits'])
        local = self.settings['local']['commit.gpgsign']
        self.signing.setCurrentIndex(0 if local is None else 1 if local.lower() in ('true', 'yes', 'on', '1') else 2)
        form.addRow('Commit signing', self.signing)
        self.signing_key = qt.QLineEdit(effective['user.signingkey'] or '')
        form.addRow('Signing key', self.signing_key)
        self.signing_format = qt.QComboBox()
        self.signing_format.addItems(['openpgp', 'ssh', 'x509'])
        self.signing_format.setCurrentText(effective['gpg.format'] or 'openpgp')
        form.addRow('Signing format', self.signing_format)
        label = qt.QLabel('Git uses your existing signing tools and keys. Key generation and agent setup are managed outside Logistics.')
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch()

    def _advanced(self, parent):
        layout = self._tab('Advanced', 'settings')
        self.inherit_identity = qt.QCheckBox('Use inherited author identity')
        self.inherit_identity.setChecked(all(self.settings['local'][key] is None for key in ('user.name', 'user.email')))
        layout.addWidget(self.inherit_identity)
        form = qt.QFormLayout()
        self.author = qt.QLineEdit(self.settings['effective']['user.name'] or '')
        self.email = qt.QLineEdit(self.settings['effective']['user.email'] or '')
        form.addRow('Name', self.author)
        form.addRow('Email', self.email)
        layout.addLayout(form)
        def identity_enabled(inherit):
            self.author.setEnabled(not inherit); self.email.setEnabled(not inherit)
        self.inherit_identity.toggled.connect(identity_enabled)
        identity_enabled(self.inherit_identity.isChecked())
        for label, relative in [('Edit .gitignore', '.gitignore')]:
            button = qt.QPushButton(label)
            button.clicked.connect(lambda checked=False, relative=relative: self._edit_file(relative))
            layout.addWidget(button)
        executable = qt.QPushButton('Git executable…')
        executable.clicked.connect(self._executable)
        layout.addWidget(executable)
        preferences = qt.QPushButton('Git preferences…')
        def open_preferences():
            self.reject(); self.parentWidget().application_settings_dialog()
        preferences.clicked.connect(open_preferences)
        layout.addWidget(preferences)
        layout.addStretch()

    def _edit_file(self, relative):
        self.reject()
        self.parentWidget().edit_file(relative)

    def _executable(self):
        # Finish this dialog before starting another job on its repository pane.
        self.reject()
        self.parentWidget().executable_dialog()

    def values(self):
        local = dict(self.settings['local'])
        mode = ('inherit', 'none', 'custom')[self.template_mode.currentIndex()]
        local['commit.template'] = None if mode == 'inherit' else '' if mode == 'none' else local['commit.template']
        local['commit.gpgsign'] = (None, 'true', 'false')[self.signing.currentIndex()]
        for key, value in [('user.signingkey', self.signing_key.text().strip()), ('gpg.format', self.signing_format.currentText())]:
            if value != (self.settings['effective'][key] or ('openpgp' if key == 'gpg.format' else '')):
                local[key] = value or None
        for key, value in [('user.name', self.author.text().strip()), ('user.email', self.email.text().strip())]:
            if self.inherit_identity.isChecked():
                local[key] = None
            elif value != (self.settings['effective'][key] or '') or all(
                    self.settings['local'][field] is None for field in ('user.name', 'user.email')):
                local[key] = value
        return {'original': {'local': self.settings['local'], 'remotes': self.settings['remotes']},
                'local': local, 'template_mode': mode, 'template_text': self.template.toPlainText(),
                'template_changed': self.template_mode.currentIndex() != self._original_template_mode or self.template.toPlainText() != self.settings['template_text'],
                'remotes': {self.remotes.topLevelItem(i).text(0): self.remotes.topLevelItem(i).text(1)
                            for i in range(self.remotes.topLevelItemCount())}}
