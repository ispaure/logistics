"""Version/platform selection around the shared layered field editor."""
from commonUtils.ui import pyside as qt
from commonUtils.ui.settings.layered_settings import LayeredSettingsEditor
from features.settings import settings_store
from features.blender.installation.releases import release_config_paths, version_from_path, releases_from_values


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
    def _build(self):
        bar = self.sections.tabBar()
        selected = bar.tabData(self.sections.currentIndex()) if self.sections.count() else None
        super()._build()
        for index in range(self.sections.count()):
            key = self.sections.tabText(index)
            bar.setTabData(index, key)
            self.sections.setTabText(index, PLATFORM_LABELS.get(key, key))
            if key == selected:
                self.sections.setCurrentIndex(index)


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
        self.note = qt.QLabel('Admin configuration: this catalog defines the Blender versions available to install. '
                             'Choose a version, then a platform. Save Settings applies only to that version. '
                             + ('Edits update this installation’s software release catalog.' if scope == 'application' else
                                'Untouched fields inherit software defaults; ↶ removes a personal override.'))
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.stack = qt.QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.empty = qt.QLabel('No version configuration files found. Add config-<version>.ini to the Blender feature.')
        self.empty.setWordWrap(True)
        self.stack.addWidget(self.empty)
        self.version.currentIndexChanged.connect(self._select_version)
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
        self.stack.setCurrentWidget(self.editors[path])

    def can_close(self):
        return all(editor.can_close() for editor in self.editors.values())


class BlenderSettings(qt.QWidget):
    """Feature configuration: existing release editors plus personal preset management."""
    def __init__(self, parent=None, *, scope='personal', directory=None, manager=None):
        super().__init__(parent)
        self.scope = scope
        self.setSizePolicy(qt.QSizePolicy.Policy.Expanding, qt.QSizePolicy.Policy.Expanding)
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = qt.QTabWidget()
        layout.addWidget(self.tabs)
        self.versions = BlenderReleaseSettings(self, scope=scope, directory=directory)
        self.tabs.addTab(self.versions, 'Versions Definitions')
        self.presets = None
        self.library = None
        self._close_pending = False
        if scope == 'personal':
            from .ui.page import BlenderPage
            self.presets = BlenderPage(self, manager=manager, settings_mode=True)
            self.presets.idle.connect(self._resume_close)
            self.tabs.insertTab(0, self.presets, 'Presets')
            from features.blender.addons.ui.page import AddonLibraryPage
            self.library = AddonLibraryPage(self.presets.library, self)
            self.tabs.addTab(self.library, 'Addon Library')
            self.tabs.setCurrentWidget(self.presets)
            self.refresh()

    def refresh(self):
        self.versions.refresh()
        if self.library is not None:
            self.library.refresh()
        if self.presets is not None and not self.presets.task.busy:
            self.presets.refresh()
            selected = getattr(self.presets.manager, 'settings_selection', None)
            if selected:
                version, name = selected
                self.presets.manager.settings_selection = None
                release = next((r for r in self.presets.releases if r.version == version), None)
                self.presets._manage_configuration(release, name)
                self.tabs.setCurrentWidget(self.presets)

    def _resume_close(self):
        if self._close_pending:
            self._close_pending = False
            qt.QTimer.singleShot(0, self.window().close)

    def can_close(self):
        if not self.versions.can_close():
            return False
        if self.presets is not None and not self.presets.prepare_close():
            self._close_pending = True
            return False
        return True
