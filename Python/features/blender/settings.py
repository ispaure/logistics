"""Version/platform selection around the shared layered field editor."""
from commonUtils.ui import pyside as qt
from commonUtils.ui.settings.layered_settings import LayeredSettingsEditor
from features.settings import settings_store
from .releases import release_config_paths, version_from_path, releases_from_values


PLATFORM_LABELS = {
    'macos-arm64': 'macOS · Apple Silicon',
    'macos-x64': 'macOS · Intel',
    'windows-x64': 'Windows · x64',
    'windows-arm64': 'Windows · ARM64',
    'linux-x64': 'Linux · x64',
    'linux-arm64': 'Linux · ARM64',
}
FIELD_LABELS = {
    'url_str': 'Download URL', 'sha256_str': 'SHA-256', 'format_str': 'Package format',
    'bundle_str': 'Extracted bundle', 'executable_str': 'Executable path',
}


class ReleaseSettingsEditor(LayeredSettingsEditor):
    platforms_changed = qt.Signal()

    def _build(self):
        selected = self.sections.tabText(self.sections.currentIndex()) if self.sections.count() else ''
        super()._build()
        self.sections.tabBar().hide()
        for index in range(self.sections.count()):
            if self.sections.tabText(index) == selected:
                self.sections.setCurrentIndex(index)
                break
        self.platforms_changed.emit()


class BlenderReleaseSettings(qt.QWidget):
    def __init__(self, parent=None, *, scope='personal', directory=None):
        super().__init__(parent)
        self.scope, self.directory = scope, directory
        self.editors = {}
        self.setSizePolicy(qt.QSizePolicy.Policy.Expanding, qt.QSizePolicy.Policy.Expanding)
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = qt.QHBoxLayout()
        row.addWidget(qt.QLabel('Blender version'))
        self.version = qt.QComboBox()
        self.version.setAccessibleName('Blender release configuration version')
        row.addWidget(self.version, 1)
        layout.addLayout(row)
        self.note = qt.QLabel('Choose a version, then a platform. Save Settings applies only to that version. '
                             + ('Edits update this installation’s software release catalog.' if scope == 'application' else
                                'Untouched fields inherit software defaults; ↶ removes a personal override.'))
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        splitter = qt.QSplitter()
        self.platforms = qt.QListWidget()
        self.platforms.setAccessibleName('Blender release platform')
        self.platforms.setMinimumWidth(170)
        self.stack = qt.QStackedWidget()
        splitter.addWidget(self.platforms)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([200, 650])
        layout.addWidget(splitter, 1)
        self.empty = qt.QLabel('No version configuration files found. Add config-<version>.ini to the Blender feature.')
        self.empty.setWordWrap(True)
        self.stack.addWidget(self.empty)
        self.version.currentIndexChanged.connect(self._select_version)
        self.platforms.currentRowChanged.connect(self._select_platform)
        self.refresh()

    def refresh(self):
        paths = release_config_paths(self.directory)
        if paths == [self.version.itemData(index) for index in range(self.version.count())]:
            return  # Retain pending edits and the platform/scroll selection.
        selected = self.version.currentData()
        with qt.QSignalBlocker(self.version):
            self.version.clear()
            for path in paths:
                self.version.addItem(version_from_path(path), path)
            index = self.version.findData(selected)
            self.version.setCurrentIndex(index if index >= 0 else 0)
        self._select_version()

    @property
    def editor(self):
        return self.editors.get(self.version.currentData())

    def _select_version(self, *_args):
        path = self.version.currentData()
        if path is None:
            self.platforms.clear()
            self.stack.setCurrentWidget(self.empty)
            return
        if path not in self.editors:
            store = settings_store(path)
            labels = {(section, key): label for section, key in store.values('application')
                      if (label := FIELD_LABELS.get(key))}
            editor = ReleaseSettingsEditor(store, self, scope=self.scope, labels=labels,
                        validator=lambda values, path=path: releases_from_values(path, values))
            self.editors[path] = editor
            self.stack.addWidget(editor)
            editor.platforms_changed.connect(self._update_platforms)
        self.stack.setCurrentWidget(self.editors[path])
        self._update_platforms()

    def _update_platforms(self):
        editor = self.editor
        if editor is None:
            return
        with qt.QSignalBlocker(self.platforms):
            self.platforms.clear()
            for index in range(editor.sections.count()):
                key = editor.sections.tabText(index)
                item = qt.QListWidgetItem(PLATFORM_LABELS.get(key, key))
                item.setData(qt.Qt.ItemDataRole.UserRole, key)
                self.platforms.addItem(item)
            self.platforms.setCurrentRow(editor.sections.currentIndex())

    def _select_platform(self, index):
        if self.editor is not None and index >= 0:
            self.editor.sections.setCurrentIndex(index)

    def can_close(self):
        return all(editor.can_close() for editor in self.editors.values())
