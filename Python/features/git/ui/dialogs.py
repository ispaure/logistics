"""Small explicit forms for repository operations."""
from commonUtils.ui import pyside as qt


class FormDialog(qt.QDialog):
    def __init__(self, title, parent=None, note='', *, scope=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(480)
        layout = qt.QVBoxLayout(self)
        if note:
            label = qt.QLabel(note)
            label.setWordWrap(True)
            label.setTextFormat(qt.Qt.TextFormat.PlainText)
            layout.addWidget(label)
        self.form = qt.QFormLayout()
        if scope is None:
            layout.addLayout(self.form)
        else:
            from commonUtils.ui.settings_sections import ScopedSettings, SettingsSection
            body = qt.QWidget(self)
            body.setLayout(self.form)
            self.sections = ScopedSettings(self)
            self.sections.set_sections([SettingsSection(scope, 'settings', 'Settings', body)])
            layout.addWidget(self.sections)
        self.buttons = qt.QDialogButtonBox(qt.QDialogButtonBox.StandardButton.Ok | qt.QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def text(self, title, value='', *, folder=False):
        edit = qt.QLineEdit(value)
        edit.setAccessibleName(title)
        if folder:
            row = qt.QWidget()
            layout = qt.QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(edit, 1)
            browse = qt.QPushButton('Browse…')
            def select():
                path = qt.QFileDialog.getExistingDirectory(self, title, edit.text())
                if path: edit.setText(path)
            browse.clicked.connect(select)
            layout.addWidget(browse)
            self.form.addRow(title, row)
        else:
            self.form.addRow(title, edit)
        return edit

    def choice(self, title, values):
        combo = qt.QComboBox()
        combo.setAccessibleName(title)
        combo.addItems(values)
        self.form.addRow(title, combo)
        return combo

    def check(self, title, checked=False):
        check = qt.QCheckBox(title)
        check.setChecked(checked)
        self.form.addRow(check)
        return check

    def submitted(self):
        return self.exec() == qt.QDialog.DialogCode.Accepted
