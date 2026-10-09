"""Sidebar settings host: session features, plain-text configuration and custom layouts."""
from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.ui.text_editor import TextFileEditor
from commonUtils.settings import settings_path
from features import registry
from .features import FeaturesPage


class ConfigurationPanel(qt.QWidget):
    def __init__(self, paths, parent=None, *, description=None):
        super().__init__(parent)
        self.editors = {}
        layout = qt.QVBoxLayout(self)
        self.files = qt.QComboBox()
        self.files.setAccessibleName('Configuration file')
        self.stack = qt.QStackedWidget()
        layout.addWidget(self.files)
        note = qt.QLabel(description or 'Edit configuration as plain text. Save explicitly. Some settings apply to the next '
                        'operation; others require restarting Logistics.')
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addWidget(self.stack, 1)
        self.add_paths(paths)
        self.files.currentIndexChanged.connect(self._select)
        if self.files.count():
            self._select(0)

    def add_paths(self, paths):
        known = {self.files.itemData(index) for index in range(self.files.count())}
        for path in dict.fromkeys(Path(path) for path in paths):
            if path not in known:
                self.files.addItem(path.name, path)

    def _select(self, index):
        path = self.files.itemData(index)
        if path is None:
            return
        if path not in self.editors:
            self.editors[path] = TextFileEditor(path, self)
            self.stack.addWidget(self.editors[path])
        self.stack.setCurrentWidget(self.editors[path])

    def can_close(self):
        return all(editor.can_close() for editor in self.editors.values())


class FeatureSettingsPanel(qt.QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.feature_name = state.name
        self.custom = {}
        self.config = None
        self.layout = qt.QVBoxLayout(self)
        self.title = qt.QLabel(state.label)
        font = self.title.font(); font.setPointSize(font.pointSize() + 5); font.setBold(True)
        self.title.setFont(font)
        self.title.setSizePolicy(qt.QSizePolicy.Policy.Preferred, qt.QSizePolicy.Policy.Maximum)
        self.layout.addWidget(self.title)
        self.status = qt.QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.status.setSizePolicy(qt.QSizePolicy.Policy.Preferred, qt.QSizePolicy.Policy.Maximum)
        self.layout.addWidget(self.status)
        self.content = qt.QVBoxLayout()
        self.layout.addLayout(self.content, 1)
        self.content.addStretch(1)
        self.refresh(state)

    def _state(self):
        return next(state for state in registry.get_feature_states() if state.name == self.feature_name)

    def refresh(self, state=None):
        state = state or self._state()
        entries = [entry.contribution for entry in registry.get_settings() if entry.feature_name == state.name]
        active = set()
        paths = []
        for entry in entries:
            active.add(entry.settings_id)
            paths.extend(entry.config_files)
            if entry.settings_id not in self.custom:
                widget = entry.create_widget(self)
                self.custom[entry.settings_id] = widget
                # Labels stay compact; custom layouts with expanding controls fill the page.
                expands = widget.sizePolicy().expandingDirections()
                if widget.layout() is not None:
                    expands |= widget.layout().expandingDirections()
                stretch = int(bool(expands & qt.Qt.Orientation.Vertical))
                self.content.insertWidget(self.content.count() - 1, widget, stretch)
            widget = self.custom[entry.settings_id]
            widget.show()
            refresh = getattr(widget, 'refresh', None)
            if callable(refresh):
                refresh()
        for key, widget in self.custom.items():
            widget.setVisible(key in active)
        conventional = Path(registry.__file__).parent / state.name / 'config.ini'
        if conventional.is_file():
            paths.append(conventional)
        if self.config is None and paths:
            self.config = ConfigurationPanel(paths, self)
            self.content.insertWidget(self.content.count() - 1, self.config, 1)
        elif self.config is not None:
            self.config.add_paths(paths)
        if not state.available:
            self.status.setText('Required feature dependencies are unavailable.')
        elif not state.enabled:
            self.status.setText('Enable this feature under Features to show its custom settings. Existing edits are retained.')
        elif not entries and not paths:
            self.status.setText('This feature has no additional settings. Use Configuration for shared application settings.')
        else:
            self.status.setText('')

        self.status.setVisible(bool(self.status.text()))
        expanding = self.config is not None or any(
            key in active and self.content.stretch(self.content.indexOf(widget))
            for key, widget in self.custom.items()
        )
        self.content.setStretch(self.content.count() - 1, 0 if expanding else 1)

    def can_close(self):
        if self.config is not None and not self.config.can_close():
            return False
        return all(getattr(widget, 'can_close', lambda: True)() for widget in self.custom.values())


class SettingsPage(qt.QWidget):
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
            for key, title in (('features', 'Features'), ('configuration', 'Configuration'),
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
            elif key == 'configuration':
                source = Path(__file__).resolve().parents[2]
                panel = ConfigurationPanel([source / 'configFile.ini', source / 'maintenance.ini',
                                            source.parent / 'launch_config.ini'], self)
            elif key == 'commonutils':
                panel = ConfigurationPanel([settings_path()], self, description=
                    'Shared wheel navigation settings. Each wheel notch turns one page. Smooth scrolling '
                    'defaults to 20× sensitivity. Edit the INI below and save explicitly; changes apply '
                    'on the next scroll, including in open comic readers. Invalid values use defaults.')
            else:
                state = next(state for state in registry.get_feature_states() if key == f'feature:{state.name}')
                panel = FeatureSettingsPanel(state, self)
            self.panels[key] = panel
            self.stack.addWidget(panel)
        self.stack.setCurrentWidget(self.panels[key])

    def can_close(self):
        return all(getattr(panel, 'can_close', lambda: True)() for panel in self.panels.values())
