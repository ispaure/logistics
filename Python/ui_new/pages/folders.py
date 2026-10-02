"""
Folders page for the replacement Logistics UI.
"""

from collections import Counter

from commonUtils import ui
from commonUtils.ui import pyside

from features import registry
from features.contributions import UIAction
from services.folder_entries import get_folder_entries
from ui_new import workflows


LOCAL_SOURCE_NAME = 'Local'


class FoldersPage(pyside.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.source_tabs = pyside.QTabBar()
        self.source_tabs.setExpanding(False)
        self.source_tabs.setAccessibleName('Folder sources')
        self.credential_combo = pyside.QComboBox()
        self.credential_label = pyside.QLabel('Credential')
        self._remote_sources = []
        self._local_sources = []
        self._local_folders = []
        self._remote_names = set()
        self._selected_entry_key = None
        self._initial_show_pending = True

        self.folder_tree = pyside.QTreeWidget()
        self.folder_tree.setHeaderHidden(True)
        self.folder_tree.setMinimumWidth(220)
        self.folder_tree.setMaximumWidth(320)

        self.selected_entry_name = None
        self._entry_items = {}

        self.detail_scroll = pyside.QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(pyside.QFrame.Shape.NoFrame)

        self._build_layout()
        self._connect_signals()
        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        if self._initial_show_pending:
            self._initial_show_pending = False
            self.refresh()

    def _build_layout(self):
        root_layout = pyside.QHBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(16)

        left_widget = pyside.QWidget()
        left_layout = pyside.QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        title_label = pyside.QLabel('Folders')
        title_font = title_label.font()
        title_font.setPointSize(title_font.pointSize() + 4)
        title_font.setBold(True)
        title_label.setFont(title_font)

        source_font = self.credential_label.font()
        source_font.setBold(True)
        self.credential_label.setFont(source_font)

        left_layout.addWidget(title_label)
        left_layout.addWidget(self.source_tabs)
        left_layout.addWidget(self.credential_label)
        left_layout.addWidget(self.credential_combo)
        left_layout.addWidget(self.folder_tree)

        splitter = pyside.QSplitter(pyside.Qt.Orientation.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(self.detail_scroll)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([250, 750])

        root_layout.addWidget(splitter)

    def _connect_signals(self):
        self.source_tabs.currentChanged.connect(self._source_changed)
        self.credential_combo.currentIndexChanged.connect(self._credential_changed)
        self.folder_tree.currentItemChanged.connect(self._selection_changed)

    def refresh(self):
        """Refresh source groups while preserving the selected credential and folder."""

        selected_source_name = self.source_tabs.tabText(self.source_tabs.currentIndex()) or LOCAL_SOURCE_NAME
        selected_credential = self.credential_combo.currentData()
        self._remote_sources = [
            (registered.feature_name, registered.contribution.name, source)
            for registered in registry.get_remote_folder_sources()
            for source in registered.contribution.get_sources()
        ]
        self._remote_names = {
            name
            for feature_name, _label, source in self._remote_sources
            for name in source.get_remote_names()
        }
        self._local_sources = [
            (registered.feature_name, registered.contribution.name,
             source, list(source.get_local_folders()))
            for registered in registry.get_local_folder_sources()
            for source in registered.contribution.get_sources()
        ]
        local_entries = get_folder_entries()
        self._local_folders = [entry.local for entry in local_entries if entry.local is not None]
        self.source_tabs.blockSignals(True)
        while self.source_tabs.count():
            self.source_tabs.removeTab(0)
        if self._get_local_only_entries():
            index = self.source_tabs.addTab(LOCAL_SOURCE_NAME)
            self.source_tabs.setTabData(index, ('local', None))

        groups = {}
        for feature, label, source, folders in self._local_sources:
            entries = self._get_unresolved_local_entries(folders)
            if entries:
                groups.setdefault((feature, label), []).extend(entries)
        for (feature, label), entries in groups.items():
            index = self.source_tabs.addTab(label)
            self.source_tabs.setTabData(index, ('local_source', feature, entries))

        groups = {}
        for feature, label, source in self._remote_sources:
            groups.setdefault((feature, label), []).append(source)
        for (feature, label), sources in groups.items():
            index = self.source_tabs.addTab(label)
            self.source_tabs.setTabData(index, ('remote', feature, sources))

        self.source_tabs.setCurrentIndex(self._find_source_index(selected_source_name))
        self.source_tabs.blockSignals(False)
        self.source_tabs.setVisible(self.source_tabs.count() > 0)
        self._refresh_credentials(selected_credential)
        self._refresh_folder_tree()

    def _find_source_index(self, source_name: str) -> int:
        for index in range(self.source_tabs.count()):
            if self.source_tabs.tabText(index) == source_name:
                return index
        return 0

    def _source_changed(self, _index):
        self._refresh_credentials()
        self._refresh_folder_tree()

    def _credential_changed(self, _index):
        self._refresh_folder_tree()

    def _get_selected_source(self):
        return self.source_tabs.tabData(self.source_tabs.currentIndex())

    def _refresh_credentials(self, selected_credential=None):
        """A newly chosen remote source always starts with all credentials."""

        selected_source = self._get_selected_source()
        is_remote = selected_source is not None and selected_source[0] == 'remote'
        self.credential_combo.blockSignals(True)
        self.credential_combo.clear()
        if is_remote:
            self.credential_combo.addItem('All', None)
            for source in selected_source[2]:
                self.credential_combo.addItem(source.name, source.context)
            if selected_credential is not None:
                for index in range(1, self.credential_combo.count()):
                    if self.credential_combo.itemData(index) == selected_credential:
                        self.credential_combo.setCurrentIndex(index)
                        break
        self.credential_combo.blockSignals(False)
        self.credential_label.setVisible(is_remote)
        self.credential_combo.setVisible(is_remote)

    def _get_unresolved_local_entries(self, folders):
        return [
            entry for entry in get_folder_entries(local_folders=folders)
            if entry.name not in self._remote_names
        ]

    def _get_local_only_entries(self):
        """Hide local folders represented by a remote or a dedicated local source."""

        source_paths = {
            folder.path
            for _feature, _label, _source, folders in self._local_sources
            for folder in folders
        }
        return self._get_unresolved_local_entries([
            folder for folder in self._local_folders if folder.path not in source_paths
        ])

    @staticmethod
    def _entry_key(entry):
        """Keep same-named folders from different credentials independently selectable."""

        return (entry.name, entry.remote_source, str(entry.remote_context),
                str(entry.local.path) if entry.local is not None else None)

    def _refresh_folder_tree(self):
        selected_source = self._get_selected_source()
        source_type = selected_source[0] if selected_source is not None else 'local'
        entry_labels = {}

        if source_type == 'local':
            entries = self._get_local_only_entries()
        elif source_type == 'local_source':
            entries = selected_source[2]
            for entry in entries:
                entry_labels[self._entry_key(entry)] = str(entry.local.path)
        else:
            _source_type, feature_name, sources = selected_source
            selected_credential = self.credential_combo.currentData()
            entries = []
            for source in sources:
                if selected_credential is not None and source.context != selected_credential:
                    continue
                source_entries = get_folder_entries(
                    source.get_remote_names(),
                    remote_source=feature_name,
                    remote_context=source.context,
                    include_local_only=False,
                    local_folders=self._local_folders
                )
                entries.extend(source_entries)
                for entry in source_entries:
                    entry_labels[self._entry_key(entry)] = source.name

        entries.sort(key=lambda entry: (entry.name, str(entry.remote_context)))
        name_counts = Counter(entry.name for entry in entries)

        self.folder_tree.clear()
        self._entry_items = {}

        if not entries:
            self.selected_entry_name = None
            self._show_empty_state()
            return

        tree_items = {}

        for entry in entries:
            name_parts = entry.name.split('-')
            parent_item = None
            path_parts = []
            entry_key = self._entry_key(entry)

            for index, name_part in enumerate(name_parts):
                path_parts.append(name_part)
                item_path = tuple(path_parts)
                is_leaf = index == len(name_parts) - 1
                if is_leaf and name_counts[entry.name] > 1:
                    item_path = (*item_path, entry_key)
                    name_part = f'{name_part} [{entry_labels[entry_key]}]'

                item = tree_items.get(item_path)

                if item is None:
                    item = pyside.QTreeWidgetItem([name_part])
                    tree_items[item_path] = item

                    if parent_item is None:
                        self.folder_tree.addTopLevelItem(item)
                    else:
                        parent_item.addChild(item)

                if index == len(name_parts) - 1:
                    item.setData(0, pyside.Qt.ItemDataRole.UserRole, entry)
                    self._entry_items[entry_key] = item

                parent_item = item

        for item in tree_items.values():
            if item.data(0, pyside.Qt.ItemDataRole.UserRole) is None:
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)

        self.folder_tree.expandAll()

        selected_item = self._entry_items.get(self._selected_entry_key)

        if selected_item is None:
            first_entry = entries[0]
            self.selected_entry_name = first_entry.name
            self._selected_entry_key = self._entry_key(first_entry)
            selected_item = self._entry_items[self._selected_entry_key]

        self.folder_tree.setCurrentItem(selected_item)

    def _selection_changed(self, current, _previous):
        if current is None:
            return

        entry = current.data(0, pyside.Qt.ItemDataRole.UserRole)

        if entry is None:
            return

        self.selected_entry_name = entry.name
        self._selected_entry_key = self._entry_key(entry)
        self._show_entry(entry)

    def _show_empty_state(self):
        widget = pyside.QWidget()
        layout = pyside.QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)

        selected_source = self._get_selected_source()
        source_type = selected_source[0] if selected_source is not None else 'local'

        if source_type == 'local':
            message = (
                'No local-only folders were found. Local folders already '
                'available through a loaded remote source are hidden here.'
            )
        elif source_type == 'local_source':
            message = 'No folders were found for this local source.'
        else:
            message = 'No configured remote folders were found for this source.'

        label = pyside.QLabel(message)
        label.setWordWrap(True)

        layout.addWidget(label)
        layout.addStretch()

        self.detail_scroll.setWidget(widget)

    def _show_entry(self, entry):
        widget = pyside.QWidget()
        layout = pyside.QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(14)

        title_label = pyside.QLabel(entry.name)
        title_font = title_label.font()
        title_font.setPointSize(title_font.pointSize() + 7)
        title_font.setBold(True)
        title_label.setFont(title_font)

        layout.addWidget(title_label)
        layout.addWidget(self._create_general_section(entry))

        contributions = sorted(
            registry.get_folder_features(),
            key=lambda registered: (
                registered.contribution.order,
                registered.contribution.name.casefold()
            )
        )

        for registered in contributions:
            contribution = registered.contribution

            if not contribution.is_available(entry):
                continue

            if contribution.create_widget is not None:
                feature_widget = contribution.create_widget(entry, self)

                if feature_widget is not None:
                    layout.addWidget(feature_widget)

                continue

            actions = contribution.get_actions(entry)

            if not actions:
                continue

            layout.addWidget(
                self._create_action_section(
                    contribution.name,
                    actions,
                    entry.name,
                    horizontal=contribution.actions_horizontal
                )
            )

        layout.addStretch()
        self.detail_scroll.setWidget(widget)

    def _create_general_section(self, entry):
        group = pyside.QGroupBox('General')
        layout = pyside.QVBoxLayout(group)
        layout.setSpacing(8)

        status_layout = pyside.QGridLayout()

        status_layout.addWidget(pyside.QLabel('Local:'), 0, 0)
        status_layout.addWidget(
            pyside.QLabel('Available' if entry.has_local else 'Not available'),
            0,
            1
        )

        status_layout.addWidget(pyside.QLabel('Remote:'), 1, 0)
        status_layout.addWidget(
            pyside.QLabel('Configured' if entry.has_remote else 'Not configured'),
            1,
            1
        )

        next_row = 2

        if entry.local is not None:
            status_layout.addWidget(pyside.QLabel('Local path:'), next_row, 0)

            path_label = pyside.QLabel(str(entry.local.path))
            path_label.setTextInteractionFlags(
                pyside.Qt.TextInteractionFlag.TextSelectableByMouse
            )
            path_label.setWordWrap(True)
            status_layout.addWidget(path_label, next_row, 1)

            next_row += 1

        if entry.remote_name is not None:
            status_layout.addWidget(pyside.QLabel('Remote name:'), next_row, 0)

            remote_label = pyside.QLabel(entry.remote_name)
            remote_label.setTextInteractionFlags(
                pyside.Qt.TextInteractionFlag.TextSelectableByMouse
            )
            status_layout.addWidget(remote_label, next_row, 1)

        status_layout.setColumnStretch(1, 1)
        layout.addLayout(status_layout)

        if entry.local is not None:
            open_button = pyside.QPushButton('Open Folder')
            open_button.clicked.connect(
                lambda _checked=False, folder=entry.local: folder.open()
            )
            layout.addWidget(open_button)

        return group

    def _create_action_section(
        self,
        title: str,
        actions: list[UIAction],
        entry_name: str,
        horizontal: bool = False
    ):
        group = pyside.QGroupBox(title)
        layout = pyside.QHBoxLayout(group) if horizontal else pyside.QVBoxLayout(group)
        layout.setSpacing(8)

        for action in actions:
            button = pyside.QPushButton(action.name)
            button.setEnabled(action.enabled)

            if action.description is not None:
                button.setToolTip(action.description)

            button.clicked.connect(
                lambda _checked=False, action=action, entry_name=entry_name:
                self._execute_action(action, entry_name)
            )

            layout.addWidget(button)

        return group

    def _execute_action(self, action: UIAction, entry_name: str):
        if action.workflow_id is not None:
            workflows.open_workflow(
                action.workflow_id,
                data=action.workflow_data,
                parent=self
            )
            return

        if action.destructive:
            confirmed = ui.display_msg_box_ok_cancel(
                'Confirm Action',
                f'Run "{action.name}" for "{entry_name}"?\n\n'
                'This action may modify files.'
            )

            if not confirmed:
                return

        action.callback()

        if action.destructive:
            self.refresh()
