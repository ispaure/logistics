"""Sidebar settings host: session features, structured INI configuration and custom layouts."""
from pathlib import Path
from commonUtils.ui import pyside as qt
from features.application import registry
from .features import FeaturesPage
from desktop.settings.appearance import AppearanceSettingsPanel
from desktop.settings.configuration import ConfigurationPanel
from desktop.settings.feature_settings import FeatureSettingsPanel
from desktop.settings.indexing import IndexSettingsPanel
from desktop.settings.workspaces import WorkspaceSettingsPanel
from commonUtils.ui.settings.layered_settings import LayeredSettingsEditor
from features.settings import initialize_settings
from services.preferences import reset_personal_preferences


# Keep the historical import alongside the visible category name.
CommonUtilsPanel = AppearanceSettingsPanel


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
        from commonUtils.ui.settings.navigation import SettingsNavigation
        splitter = SettingsNavigation(self)
        layout.addWidget(splitter, 1)
        self.sidebar = splitter.sidebar
        from commonUtils.ui.appearance.styling import bind_font
        bind_font(self.sidebar, 'ui')
        self.sidebar.setHeaderHidden(True)
        self.sidebar.setAccessibleName('Settings categories')
        self.sidebar.installEventFilter(self)
        self.stack = splitter.stack
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
            for key, title in (('features', 'Features'), ('reader-history', 'Reader history'), ('workspaces', 'Workspaces'), ('indexing', 'File indexing'), ('configuration', 'Configuration'),
                               ('commonutils', 'Appearance & shared controls'), ('licenses', 'Open-source licenses')):
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
            elif key == 'reader-history':
                from desktop.settings.reader_history import ReaderHistoryPanel
                panel = ReaderHistoryPanel(self)
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
                panel = AppearanceSettingsPanel(self, layered=True, scope=self.scope_selector.currentData())
            elif key == 'licenses':
                from desktop.settings.licenses import LicensesPanel
                panel = LicensesPanel(self)
            else:
                state = next(state for state in registry.get_feature_states() if key == f'feature:{state.name}')
                panel = FeatureSettingsPanel(state, self, scope=self.scope_selector.currentData())
            self.panels[key] = panel
            self.stack.addWidget(panel)
        self.stack.setCurrentWidget(self.panels[key])

    def can_close(self):
        return all(getattr(panel, 'can_close', lambda: True)() for panel in self.panels.values())
