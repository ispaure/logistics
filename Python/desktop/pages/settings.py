"""Sidebar settings host: session features, structured INI configuration and custom layouts."""
from commonUtils.ui.appearance.typography import point_size, setting_size
from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.ui.text_editor import TextFileEditor
from commonUtils.ui.markdown import open_markdown
from commonUtils.ui.settings.ini_editor import INISettingsEditor
from commonUtils.configuration.settings import settings_path
from features.application import registry
from .features import FeaturesPage
from desktop.settings.indexing import IndexSettingsPanel
from desktop.settings.workspaces import WorkspaceSettingsPanel
from commonUtils.ui.settings.settings_sections import ScopedSettings, SettingsSection
from commonUtils.ui.settings.layered_settings import LayeredSettingsEditor
from features.settings import settings_store, initialize_settings, validate_configuration
from services.preferences import reset_personal_preferences


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


class CommonUtilsPanel(ConfigurationPanel):
    def __init__(self, parent=None, *, layered=False, scope='application'):
        super().__init__([settings_path()], parent, layered=layered, scope=scope, scoped=not layered)
        from desktop.snow import CONFIG, FIELD
        self._snow_store = settings_store(CONFIG)
        self.snow_choice = qt.QCheckBox('Seasonal snow')
        self.snow_choice.setToolTip('Snow from December 15 through January 2, inclusive. Disabled in high-contrast mode. Saved immediately.')
        self.snow_status = qt.QLabel()
        self.snow_status.setWordWrap(True)
        self.layout().insertWidget(0, self.snow_status)
        self.layout().insertWidget(0, self.snow_choice)
        self._snow_field = FIELD
        self._load_snow()
        self.snow_choice.toggled.connect(self._save_snow)
        if layered:
            return
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

    def _load_snow(self):
        with qt.QSignalBlocker(self.snow_choice):
            self.snow_choice.setChecked(self._snow_store.safe_values(self.scope).get(self._snow_field, 'true').lower() == 'true')

    def _save_snow(self, enabled):
        try:
            self._snow_store.save({self._snow_field: str(enabled).lower()}, scope=self.scope)
            self.snow_status.setText('')
        except (OSError, ValueError) as error:
            self._load_snow()
            self.snow_status.setText(str(error))

    def set_scope(self, scope):
        super().set_scope(scope)
        self.scope = scope
        if hasattr(self, 'snow_choice'):
            self._load_snow()

    def _appearance_changed(self, index):
        from commonUtils.ui.appearance.theme import apply_theme
        apply_theme(mode=self.theme_mode.itemData(index))


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


class SettingsPage(qt.QWidget):
    def show_category(self, category):
        iterator = qt.QTreeWidgetItemIterator(self.sidebar)
        while iterator.value():
            item = iterator.value()
            if item.data(0, qt.Qt.ItemDataRole.UserRole) == category:
                self.sidebar.setCurrentItem(item)
                return
            iterator += 1

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
        initialize_settings()
        self.panels = {}
        self._category_items = {}
        layout = qt.QVBoxLayout(self)
        self.scope_selector = qt.QComboBox()
        self.scope_selector.setAccessibleName('Configuration scope')
        can_edit_defaults = Path.home().name == 'marca'
        if can_edit_defaults:
            self.scope_selector.addItem('Default Software Configuration', 'application')
        self.scope_selector.addItem('Personal Settings', 'personal')
        self.scope_selector.setCurrentIndex(self.scope_selector.findData('personal'))
        self.scope_selector.setToolTip(
            'Software configuration edits tracked repository INIs. Personal settings override them in AppData.'
            if can_edit_defaults else 'Personal settings override the shipped defaults in AppData.')
        scope_row = qt.QHBoxLayout()
        scope_row.addWidget(self.scope_selector)
        scope_row.addStretch()
        self.reset_personal_button = qt.QPushButton('Reset All Personal Settings…')
        self.reset_personal_button.setToolTip('Restore defaults for every settings category, not just the current tab.')
        self.reset_personal_button.clicked.connect(self._reset_all_personal_settings)
        scope_row.addWidget(self.reset_personal_button)
        layout.addLayout(scope_row)
        self.reset_status = qt.QLabel()
        self.reset_status.setWordWrap(True)
        self.reset_status.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.reset_status.setSizePolicy(qt.QSizePolicy.Policy.Preferred, qt.QSizePolicy.Policy.Maximum)
        self.reset_status.setAlignment(qt.Qt.AlignmentFlag.AlignLeft | qt.Qt.AlignmentFlag.AlignTop)
        self.reset_status.hide()
        layout.addWidget(self.reset_status)
        self.scope_selector.currentIndexChanged.connect(self._scope_changed)
        splitter = qt.QSplitter()
        layout.addWidget(splitter, 1)
        self.sidebar = qt.QTreeWidget()
        from commonUtils.ui.appearance.styling import bind_font
        bind_font(self.sidebar, 'ui')
        self.sidebar.setHeaderHidden(True)
        self.sidebar.setAccessibleName('Settings categories')
        self.sidebar.installEventFilter(self)
        self.stack = qt.QStackedWidget()
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        self.sidebar.currentItemChanged.connect(self._selected)
        self._unsubscribe = registry.subscribe(self._changed)
        self.destroyed.connect(self._unsubscribe)
        self.refresh()

    def _scope_changed(self):
        scope = self.scope_selector.currentData()
        self.reset_personal_button.setVisible(scope == 'personal')
        for panel in self.panels.values():
            setter = getattr(panel, 'set_scope', None)
            if setter is not None:
                setter(scope)

    def _reset_all_personal_settings(self):
        if self.scope_selector.currentData() != 'personal':
            return
        answer = qt.QMessageBox.question(
            self, 'Reset All Personal Settings',
            'Reset personal settings in ALL categories to the shipped software defaults?\n\n'
            'This includes feature selection, appearance, editor options, indexing and other configuration overrides. '
            'Unsaved personal settings edits will be discarded.\n\n'
            'Your documents, accounts, workspaces, reading progress, installed software and Blender presets will be kept. '
            'Launcher settings apply on the next launch.',
            qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.No,
            qt.QMessageBox.StandardButton.No)
        if answer != qt.QMessageBox.StandardButton.Yes:
            return
        self.reset_status.show()
        try:
            result = reset_personal_preferences(refresh_callbacks=(self._reload_personal_editors, self.refresh))
        except Exception as error:
            self.reset_status.setText(f'Could not reset personal settings: {error}')
            return
        if result.refresh_errors:
            self.reset_status.setText(f'All personal settings were reset. Some views could not refresh: {"; ".join(result.refresh_errors)}. '
                                      'Restart Logistics to finish applying the defaults.')
        else:
            self.reset_status.setText('All personal settings reset to software defaults. '
                                      'Open tools reload their preferences automatically; launcher settings apply on the next launch.')

    def _reload_personal_editors(self):
        for editor in self.findChildren(LayeredSettingsEditor):
            if editor.scope == 'personal':
                editor.pending.clear()
                if not editor.reload(initial=True):
                    raise ValueError('A personal settings editor could not reload')
        appearance = self.panels.get('commonutils')
        if appearance is not None:
            appearance._load_snow()

    def _changed(self):
        qt.QTimer.singleShot(0, self.refresh)

    def _fit_sidebar(self):
        # The view's column hint includes the tree indentation and styled items.
        padding = self.sidebar.fontMetrics().horizontalAdvance('   ')
        scrollbar = self.sidebar.style().pixelMetric(qt.QStyle.PixelMetric.PM_ScrollBarExtent)
        width = self.sidebar.sizeHintForColumn(0) + padding + scrollbar + 2 * self.sidebar.frameWidth()
        self.sidebar.setFixedWidth(max(1, width))

    def eventFilter(self, watched, event):
        if watched is self.sidebar and event.type() in (qt.QEvent.Type.FontChange, qt.QEvent.Type.StyleChange):
            qt.QTimer.singleShot(0, self._fit_sidebar)
        return super().eventFilter(watched, event)

    def refresh(self):
        states = sorted((state for state in registry.get_feature_states() if state.enabled),
                        key=lambda state: state.label.casefold())
        feature_keys = {f'feature:{state.name}' for state in states}
        if self._category_items and feature_keys == {key for key in self._category_items if key.startswith('feature:')}:
            # Runtime toggles change labels, not the category structure. Retain the
            # tree items so selection, expansion and sidebar scrolling stay put.
            for state in states:
                key = f'feature:{state.name}'
                self._category_items[key].setText(0, state.label)
                self._category_items[key].setToolTip(0, getattr(state, 'description', ''))
                if key in self.panels:
                    self.panels[key].refresh(state)
            self._fit_sidebar()
            return
        scroll_position = self.sidebar.verticalScrollBar().value()
        current = self.sidebar.currentItem()
        selected = current.data(0, qt.Qt.ItemDataRole.UserRole) if current else 'features'
        with qt.QSignalBlocker(self.sidebar):
            self.sidebar.clear()
            items = {}
            for key, title in (('features', 'Features'), ('workspaces', 'Workspaces'), ('indexing', 'File indexing'), ('configuration', 'Configuration'),
                               ('commonutils', 'Appearance & shared controls')):
                item = qt.QTreeWidgetItem([title])
                item.setData(0, qt.Qt.ItemDataRole.UserRole, key)
                self.sidebar.addTopLevelItem(item)
                items[key] = item
            heading = qt.QTreeWidgetItem(['Feature settings'])
            heading.setFlags(heading.flags() & ~qt.Qt.ItemFlag.ItemIsSelectable)
            self.sidebar.addTopLevelItem(heading)
            for state in states:
                key = f'feature:{state.name}'
                item = qt.QTreeWidgetItem([state.label])
                item.setData(0, qt.Qt.ItemDataRole.UserRole, key)
                item.setToolTip(0, getattr(state, 'description', ''))
                heading.addChild(item)
                items[key] = item
                if key in self.panels:
                    self.panels[key].refresh(state)
            heading.setExpanded(True)
            self.sidebar.setCurrentItem(items.get(selected, items['features']))
            self._category_items = items
        self.sidebar.verticalScrollBar().setValue(scroll_position)
        self._fit_sidebar()
        self._selected(self.sidebar.currentItem(), None)

    def _selected(self, item, previous):
        if item is None:
            return
        key = item.data(0, qt.Qt.ItemDataRole.UserRole)
        if key is None:
            return
        if key not in self.panels:
            if key == 'features':
                panel = FeaturesPage(self, scope=self.scope_selector.currentData())
            elif key == 'workspaces':
                panel = WorkspaceSettingsPanel(self)
            elif key == 'indexing':
                panel = IndexSettingsPanel(self, scope=self.scope_selector.currentData())
            elif key == 'configuration':
                source = Path(__file__).resolve().parents[2]
                panel = ConfigurationPanel([source / 'configFile.ini', source / 'maintenance.ini',
                                            source.parent / 'launch_config.ini'], self, layered=True, scoped=False,
                                            scope=self.scope_selector.currentData())
            elif key == 'commonutils':
                panel = CommonUtilsPanel(self, layered=True, scope=self.scope_selector.currentData())
            else:
                state = next(state for state in registry.get_feature_states() if key == f'feature:{state.name}')
                panel = FeatureSettingsPanel(state, self, scope=self.scope_selector.currentData())
            self.panels[key] = panel
            self.stack.addWidget(panel)
        self.stack.setCurrentWidget(self.panels[key])

    def can_close(self):
        return all(getattr(panel, 'can_close', lambda: True)() for panel in self.panels.values())
