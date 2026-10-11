"""Sidebar settings host: session features, structured INI configuration and custom layouts."""
from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.ui.text_editor import TextFileEditor
from commonUtils.ui.markdown import open_markdown
from ui_new.settings.ini_editor import INISettingsEditor
from commonUtils.configuration.settings import settings_path
from features import registry
from .features import FeaturesPage
from ui_new.settings.indexing import IndexSettingsPanel
from commonUtils.ui.settings_sections import ScopedSettings, SettingsSection


class ConfigurationPanel(qt.QWidget):
    def __init__(self, paths, parent=None, *, description=None, scoped=True, scope="application"):
        super().__init__(parent)
        self.editors = {}
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
        if path not in self.editors:
            editor_type = INISettingsEditor if path.suffix.lower() == '.ini' else TextFileEditor
            self.editors[path] = editor_type(path, self)
            self.stack.addWidget(self.editors[path])
        self.location = self.editors[path].path_label
        self.location.setToolTip(str(path.absolute()))
        self.stack.setCurrentWidget(self.editors[path])

    def can_close(self):
        return all(editor.can_close() for editor in self.editors.values())


class CommonUtilsPanel(ConfigurationPanel):
    def __init__(self, parent=None):
        super().__init__([settings_path()], parent)
        appearance = qt.QHBoxLayout()
        appearance.addWidget(qt.QLabel('Appearance (session)'))
        self.theme_mode = qt.QComboBox()
        self.theme_mode.setAccessibleName('Appearance mode')
        for label, mode in [('System', 'system'), ('Light', 'light'), ('Dark', 'dark')]:
            self.theme_mode.addItem(label, mode)
        controller = getattr(qt.QApplication.instance(), '_commonutils_theme', None)
        self.theme_mode.setCurrentIndex(self.theme_mode.findData(controller.mode if controller else 'system'))
        self.theme_mode.currentIndexChanged.connect(self._appearance_changed)
        appearance.addWidget(self.theme_mode)
        appearance.addStretch()
        self.layout().insertLayout(0, appearance)

    def _appearance_changed(self, index):
        from commonUtils.ui.theme import apply_theme
        apply_theme(mode=self.theme_mode.itemData(index))


class FeatureSettingsPanel(qt.QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.feature_name = state.name
        self.custom = {}
        self.config = None
        self.configs = {}
        self.bodies = {}
        self.sections = ScopedSettings(self)
        self.settings_tabs = self.sections.tabs
        self.layout = qt.QVBoxLayout(self)
        self.title = qt.QLabel(state.label)
        font = self.title.font(); font.setPointSize(font.pointSize() + 5); font.setBold(True)
        self.title.setFont(font)
        self.title.setSizePolicy(qt.QSizePolicy.Policy.Preferred, qt.QSizePolicy.Policy.Maximum)
        header = qt.QHBoxLayout()
        header.addWidget(self.title, 1)
        self.guide = Path(registry.__file__).parent / state.name / 'user_docs' / 'index.md'
        self.guide_button = qt.QPushButton('User Guide')
        self.guide_button.setAccessibleName(f'{state.label} user guide')
        self.guide_button.setEnabled(self.guide.is_file())
        self.guide_button.setToolTip('Open user documentation (hold Alt to edit)' if self.guide.is_file()
                                     else 'No user guide is installed.')
        self.guide_button.clicked.connect(lambda: open_markdown(self.guide, parent=self.window(), detached=True, allow_new_tabs=False))
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

    def _state(self):
        return next(state for state in registry.get_feature_states() if state.name == self.feature_name)

    def refresh(self, state=None):
        state = state or self._state()
        members = getattr(state, 'members', ()) or (state.name,)
        entries = [entry.contribution for entry in registry.get_settings() if entry.feature_name in members]
        paths = {'application': [], 'personal': []}
        for entry in entries:
            scope = entry.config_scope or entry.scope
            paths[scope].extend(entry.config_files)
            if entry.create_widget is not None and entry.settings_id not in self.custom:
                self.custom[entry.settings_id] = entry.create_widget(self)
            refresh = getattr(self.custom.get(entry.settings_id), 'refresh', None)
            if callable(refresh):
                refresh()
        for member in members:
            conventional = Path(registry.__file__).parent / member / 'config.ini'
            if conventional.is_file():
                paths['application'].append(conventional)
        for scope, files in paths.items():
            if files and scope not in self.configs:
                self.configs[scope] = ConfigurationPanel(files, self, scoped=False)
            elif files:
                self.configs[scope].add_paths(files)
        self.config = self.configs.get('application') or self.configs.get('personal')
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
            inline = [entry for entry in entries if entry.scope == scope and not entry.separate_tab
                      and entry.settings_id in self.custom]
            config = self.configs.get(scope)
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
                                                'INI files' if config else 'Settings', body, nested=config is not None))
            for entry in entries:
                if entry.scope == scope and entry.separate_tab and entry.settings_id in self.custom:
                    sections.append(SettingsSection(scope, entry.settings_id, entry.name,
                                                    self.custom[entry.settings_id]))
        self.sections.set_sections(sections)
        # Tab pages own visibility: showing every retained custom widget would
        # overlap inactive pages when refreshing the feature registry.
        for scope in self.sections.pages.values():
            current = scope.tabs.currentWidget() if scope.tabs.count() else scope.direct
            if current is not None:
                current.show()
        self.body = self.bodies.get('application') or self.bodies.get('personal')
        if not state.available:
            self.status.setText('Required feature dependencies are unavailable.')
        elif not state.enabled:
            self.status.setText('Enable this feature under Features.')
        elif not entries and not self.configs:
            self.status.setText('No additional settings.')
        else:
            self.status.setText('')
        self.status.setVisible(bool(self.status.text()))

    def can_close(self):
        if not all(config.can_close() for config in self.configs.values()):
            return False
        return all(getattr(widget, 'can_close', lambda: True)() for widget in self.custom.values())


class SettingsPage(qt.QWidget):
    def show_feature(self, name):
        iterator = qt.QTreeWidgetItemIterator(self.sidebar)
        while iterator.value():
            item = iterator.value()
            if item.data(0, qt.Qt.ItemDataRole.UserRole) == f'feature:{name}':
                self.sidebar.setCurrentItem(item)
                return
            iterator += 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.panels = {}
        layout = qt.QHBoxLayout(self)
        splitter = qt.QSplitter()
        layout.addWidget(splitter)
        self.sidebar = qt.QTreeWidget()
        self.sidebar.setHeaderHidden(True)
        self.sidebar.setAccessibleName('Settings categories')
        self.sidebar.setMinimumWidth(190)
        self.stack = qt.QStackedWidget()
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 850])
        self.sidebar.currentItemChanged.connect(self._selected)
        self._unsubscribe = registry.subscribe(self._changed)
        self.destroyed.connect(self._unsubscribe)
        self.refresh()

    def _changed(self):
        qt.QTimer.singleShot(0, self.refresh)

    def refresh(self):
        current = self.sidebar.currentItem()
        selected = current.data(0, qt.Qt.ItemDataRole.UserRole) if current else 'features'
        with qt.QSignalBlocker(self.sidebar):
            self.sidebar.clear()
            items = {}
            for key, title in (('features', 'Features'), ('indexing', 'File indexing'), ('configuration', 'Configuration'),
                               ('commonutils', 'commonUtils')):
                item = qt.QTreeWidgetItem([title])
                item.setData(0, qt.Qt.ItemDataRole.UserRole, key)
                self.sidebar.addTopLevelItem(item)
                items[key] = item
            heading = qt.QTreeWidgetItem(['Feature settings'])
            heading.setFlags(heading.flags() & ~qt.Qt.ItemFlag.ItemIsSelectable)
            self.sidebar.addTopLevelItem(heading)
            for state in sorted(registry.get_feature_states(), key=lambda state: state.label.casefold()):
                key = f'feature:{state.name}'
                item = qt.QTreeWidgetItem([state.label + (' (disabled)' if not state.enabled else '')])
                item.setData(0, qt.Qt.ItemDataRole.UserRole, key)
                heading.addChild(item)
                items[key] = item
                if key in self.panels:
                    self.panels[key].refresh(state)
            heading.setExpanded(True)
            self.sidebar.setCurrentItem(items.get(selected, items['features']))
        self._selected(self.sidebar.currentItem(), None)

    def _selected(self, item, previous):
        if item is None:
            return
        key = item.data(0, qt.Qt.ItemDataRole.UserRole)
        if key is None:
            return
        if key not in self.panels:
            if key == 'features':
                panel = FeaturesPage(self)
            elif key == 'indexing':
                panel = IndexSettingsPanel(self)
            elif key == 'configuration':
                source = Path(__file__).resolve().parents[2]
                panel = ConfigurationPanel([source / 'configFile.ini', source / 'maintenance.ini',
                                            source.parent / 'launch_config.ini'], self)
            elif key == 'commonutils':
                panel = CommonUtilsPanel(self)
            else:
                state = next(state for state in registry.get_feature_states() if key == f'feature:{state.name}')
                panel = FeatureSettingsPanel(state, self)
            self.panels[key] = panel
            self.stack.addWidget(panel)
        self.stack.setCurrentWidget(self.panels[key])

    def can_close(self):
        return all(getattr(panel, 'can_close', lambda: True)() for panel in self.panels.values())
