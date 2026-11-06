"""Settings contributed by enabled desktop features."""
from commonUtils.ui import pyside as qt
from commonUtils.ui.appearance.typography import point_size, setting_size
from commonUtils.ui.markdown import open_markdown
from commonUtils.ui.settings.settings_sections import ScopedSettings, SettingsSection
from .configuration import ConfigurationPanel
from features.application import registry


class FeatureSettingsPanel(qt.QWidget):
    def __init__(self, state, parent=None, *, scope=None):
        super().__init__(parent)
        self.feature_name = state.name
        self.selected_scope = scope
        self.custom = {}
        self.config = None
        self.configs = {}
        self.bodies = {}
        self.sections = ScopedSettings(self)
        self.settings_tabs = self.sections.tabs
        self.layout = qt.QVBoxLayout(self)
        self.title = qt.QLabel(state.label)
        font = self.title.font(); font.setPointSizeF(point_size(setting_size(font) + 3.75)); font.setBold(True)
        self.title.setFont(font)
        self.title.setSizePolicy(qt.QSizePolicy.Policy.Preferred, qt.QSizePolicy.Policy.Maximum)
        header = qt.QHBoxLayout()
        header.addWidget(self.title, 1)
        from services.documentation import feature_guide
        self.guide, self.guide_directory = feature_guide(registry.feature_root / state.name)
        self.guide_button = qt.QPushButton('User Guide')
        self.guide_button.setAccessibleName(f'{state.label} user guide')
        self.guide_button.setEnabled(self.guide.is_file())
        self.guide_button.setToolTip('Open user documentation (hold Alt to edit)' if self.guide.is_file()
                                     else 'No user guide is installed.')
        self.guide_button.clicked.connect(lambda: open_markdown(self.guide, directory=self.guide_directory, parent=self.window(), detached=True, allow_new_tabs=False))
        header.addWidget(self.guide_button)
        self.layout.addLayout(header)
        self.status = qt.QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.status.setSizePolicy(qt.QSizePolicy.Policy.Preferred, qt.QSizePolicy.Policy.Maximum)
        self.layout.addWidget(self.status)
        self.body = None
        self.layout.addWidget(self.sections, 1)
        self.refresh(state)

    def set_scope(self, scope):
        self.selected_scope = scope
        self.refresh()

    def _state(self):
        return next(state for state in registry.get_feature_states() if state.name == self.feature_name)

    def refresh(self, state=None):
        state = state or self._state()
        members = getattr(state, 'members', ()) or (state.name,)
        entries = [entry.contribution for entry in registry.get_settings() if entry.feature_name in members]
        self._refresh_editor_sources(entries, members)
        self._project_feature_settings(entries)
        if not state.available:
            self.status.setText('Required feature dependencies are unavailable.')
        elif not state.enabled:
            self.status.setText('Enable this feature under Features.')
        elif not entries and not self.configs:
            self.status.setText('No additional settings.')
        else:
            self.status.setText('')
        self.status.setVisible(bool(self.status.text()))

    def _refresh_editor_sources(self, entries, members):
        """Refresh contributed widgets and scoped INI editors without replacing retained buffers."""
        paths = {'application': [], 'personal': []}
        for entry in entries:
            scope = entry.config_scope or entry.scope
            paths[scope].extend(entry.config_files)
            if entry.create_widget is not None and entry.settings_id not in self.custom:
                self.custom[entry.settings_id] = entry.create_widget(self)
                central = getattr(self.custom[entry.settings_id], 'use_systemic_editor', None)
                if self.selected_scope is not None and callable(central):
                    central()
            refresh = getattr(self.custom.get(entry.settings_id), 'refresh', None)
            if callable(refresh):
                refresh()
        for member in members:
            conventional = registry.feature_root / member / 'config.ini'
            if conventional.is_file():
                paths['application'].append(conventional)
        for scope, files in paths.items():
            if files and scope not in self.configs:
                self.configs[scope] = ConfigurationPanel(files, self, scoped=False,
                    layered=self.selected_scope is not None, scope=self.selected_scope or scope)
            elif files:
                self.configs[scope].add_paths(files)
        self.config = self.configs.get('application') or self.configs.get('personal')
        if self.selected_scope is not None:
            for config in self.configs.values():
                config.set_scope(self.selected_scope)

    def _project_feature_settings(self, entries):
        """Reparent retained controls into scoped sections and reveal only active tab pages."""
        # Keep every editor and custom widget alive during enable/disable updates.
        for body in self.bodies.values():
            content = body.layout()
            while content.count():
                item = content.takeAt(0)
                if item.widget() is not None:
                    item.widget().hide()
        for widget in self.custom.values():
            widget.hide()
        sections = []
        for scope in ('application', 'personal'):
            if self.selected_scope is not None and scope != self.selected_scope:
                continue
            inline = [entry for entry in entries if entry.scope == scope and not entry.separate_tab
                      and entry.settings_id in self.custom]
            config = (self.configs.get('application') or self.configs.get('personal')) if self.selected_scope is not None else self.configs.get(scope)
            if inline or config is not None:
                if scope not in self.bodies:
                    body = self.bodies[scope] = qt.QWidget(self)
                    content = qt.QVBoxLayout(body)
                    content.setContentsMargins(0, 0, 0, 0)
                body = self.bodies[scope]
                content = body.layout()
                expands = False
                for entry in inline:
                    widget = self.custom[entry.settings_id]
                    directions = widget.sizePolicy().expandingDirections()
                    if widget.layout() is not None:
                        directions |= widget.layout().expandingDirections()
                    stretch = int(bool(directions & qt.Qt.Orientation.Vertical))
                    content.addWidget(widget, stretch)
                    widget.show()
                    expands |= bool(stretch)
                if config is not None:
                    content.addWidget(config, 1)
                    config.show()
                    expands = True
                content.addStretch(0 if expands else 1)
                sections.append(SettingsSection(scope, 'ini' if config else 'settings',
                                                'Options' if self.selected_scope is not None else 'INI files' if config else 'Settings', body, nested=config is not None))
            for entry in entries:
                if entry.scope == scope and entry.separate_tab and entry.settings_id in self.custom:
                    sections.append(SettingsSection(scope, entry.settings_id, entry.name,
                                                    self.custom[entry.settings_id]))
        self.sections.set_sections(sections)
        if self.selected_scope is not None:
            self.settings_tabs.tabBar().hide()
        # Tab pages own visibility: showing every retained custom widget would
        # overlap inactive pages when refreshing the feature registry.
        for scope in self.sections.pages.values():
            current = scope.tabs.currentWidget() if scope.tabs.count() else scope.direct
            if current is not None:
                current.show()
        self.body = self.bodies.get('application') or self.bodies.get('personal')

    def can_close(self):
        if not all(config.can_close() for config in self.configs.values()):
            return False
        return all(getattr(widget, 'can_close', lambda: True)() for widget in self.custom.values())
