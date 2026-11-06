"""Settings → Configuration: retained file editors and application/personal scopes."""
from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.ui.text_editor import TextFileEditor
from commonUtils.ui.settings.ini_editor import INISettingsEditor
from commonUtils.ui.settings.settings_sections import ScopedSettings, SettingsSection
from commonUtils.ui.settings.layered_settings import LayeredSettingsEditor
from features.settings import settings_store, validate_configuration


class ConfigurationPanel(qt.QWidget):
    def __init__(self, paths, parent=None, *, description=None, scoped=True, scope="application", layered=False):
        super().__init__(parent)
        self.editors = {}
        self.layered, self.scope = layered, scope
        self._scope_editors = {}
        layout = qt.QVBoxLayout(self)
        body = qt.QWidget(self)
        content = qt.QVBoxLayout(body)
        content.setContentsMargins(12, 10, 12, 10)
        self.files = qt.QComboBox()
        self.files.setAccessibleName('Configuration file')
        self.stack = qt.QStackedWidget()
        content.addWidget(self.files)
        if description:
            note = qt.QLabel(description)
            note.setWordWrap(True)
            content.addWidget(note)
        content.addWidget(self.stack, 1)
        self.sections = None
        if scoped:
            self.sections = ScopedSettings(self)
            self.sections.set_sections([SettingsSection(scope, 'ini', 'INI files', body, nested=True)])
            layout.addWidget(self.sections)
        else:
            layout.addWidget(body)
        self.add_paths(paths)
        self.files.currentIndexChanged.connect(self._select)
        if self.files.count():
            self._select(0)

    def add_paths(self, paths):
        known = {self.files.itemData(index) for index in range(self.files.count())}
        for path in dict.fromkeys(Path(path) for path in paths):
            if path not in known:
                self.files.addItem(path.name, path)
        self.files.setVisible(self.files.count() > 1)

    def _select(self, index):
        path = self.files.itemData(index)
        if path is None:
            return
        identity = path, self.scope
        if self.layered:
            if identity not in self._scope_editors:
                editor = LayeredSettingsEditor(settings_store(path), self, scope=self.scope,
                    validator=lambda values, path=path: validate_configuration(path, values))
                self._scope_editors[identity] = editor
                self.stack.addWidget(editor)
            self.editors[path] = self._scope_editors[identity]
        elif path not in self.editors:
            if path.suffix.lower() == '.ini':
                self.editors[path] = INISettingsEditor(path, self, typed_keys=True)
            else:
                self.editors[path] = TextFileEditor(path, self)
            self.stack.addWidget(self.editors[path])
        self.location = self.editors[path].path_label
        self.location.setToolTip(str(path.absolute()))
        self.stack.setCurrentWidget(self.editors[path])

    def set_scope(self, scope):
        if self.layered and self.scope != scope:
            self.scope = scope
            self._select(self.files.currentIndex())

    def can_close(self):
        return all(editor.can_close() for editor in (self._scope_editors.values() if self.layered else self.editors.values()))
