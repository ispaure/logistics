"""
Folders page for the replacement Logistics UI.
"""

from commonUtils import ui
from commonUtils.ui import pyside

from features import registry
from features.contributions import UIAction
from services.folder_entries import get_folder_entries
from ui_new import workflows


class FoldersPage(pyside.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

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

        left_layout.addWidget(title_label)
        left_layout.addWidget(self.folder_tree)

        splitter = pyside.QSplitter(pyside.Qt.Orientation.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(self.detail_scroll)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([250, 750])

        root_layout.addWidget(splitter)

    def _connect_signals(self):
        self.folder_tree.currentItemChanged.connect(self._selection_changed)

    def refresh(self):
        """Refresh merged folder discovery while preserving the last real folder selection."""

        remote_names = []

        for registered in registry.get_remote_folder_sources():
            remote_names.extend(registered.contribution.get_remote_names())

        entries = get_folder_entries(remote_names)

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

            for index, name_part in enumerate(name_parts):
                path_parts.append(name_part)
                item_path = tuple(path_parts)

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
                    self._entry_items[entry.name] = item

                parent_item = item

        for item in tree_items.values():
            if item.data(0, pyside.Qt.ItemDataRole.UserRole) is None:
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)

        self.folder_tree.expandAll()

        selected_item = self._entry_items.get(self.selected_entry_name)

        if selected_item is None:
            first_entry = entries[0]
            self.selected_entry_name = first_entry.name
            selected_item = self._entry_items[first_entry.name]

        self.folder_tree.setCurrentItem(selected_item)

    def _selection_changed(self, current, _previous):
        if current is None:
            return

        entry = current.data(0, pyside.Qt.ItemDataRole.UserRole)

        if entry is None:
            return

        self.selected_entry_name = entry.name
        self._show_entry(entry)

    def _show_empty_state(self):
        widget = pyside.QWidget()
        layout = pyside.QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)

        label = pyside.QLabel('No local or configured remote folders were found.')
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

            actions = contribution.get_actions(entry)

            if not actions:
                continue

            layout.addWidget(self._create_action_section(contribution.name, actions, entry.name))

        layout.addStretch()
        self.detail_scroll.setWidget(widget)

    def _create_general_section(self, entry):
        group = pyside.QGroupBox('General')
        layout = pyside.QVBoxLayout(group)
        layout.setSpacing(8)

        status_layout = pyside.QGridLayout()

        status_layout.addWidget(pyside.QLabel('Local:'), 0, 0)
        status_layout.addWidget(pyside.QLabel('Available' if entry.has_local else 'Not available'), 0, 1)

        status_layout.addWidget(pyside.QLabel('Remote:'), 1, 0)
        status_layout.addWidget(pyside.QLabel('Configured' if entry.has_remote else 'Not configured'), 1, 1)

        next_row = 2

        if entry.local is not None:
            status_layout.addWidget(pyside.QLabel('Local path:'), next_row, 0)

            path_label = pyside.QLabel(str(entry.local.path))
            path_label.setTextInteractionFlags(pyside.Qt.TextInteractionFlag.TextSelectableByMouse)
            path_label.setWordWrap(True)
            status_layout.addWidget(path_label, next_row, 1)

            next_row += 1

        if entry.remote_name is not None:
            status_layout.addWidget(pyside.QLabel('Remote name:'), next_row, 0)

            remote_label = pyside.QLabel(entry.remote_name)
            remote_label.setTextInteractionFlags(pyside.Qt.TextInteractionFlag.TextSelectableByMouse)
            status_layout.addWidget(remote_label, next_row, 1)

        status_layout.setColumnStretch(1, 1)
        layout.addLayout(status_layout)

        if entry.local is not None:
            open_button = pyside.QPushButton('Open Folder')
            open_button.clicked.connect(lambda _checked=False, folder=entry.local: folder.open())
            layout.addWidget(open_button)

        return group

    def _create_action_section(self, title: str, actions: list[UIAction], entry_name: str):
        group = pyside.QGroupBox(title)
        layout = pyside.QVBoxLayout(group)
        layout.setSpacing(8)

        for action in actions:
            button = pyside.QPushButton(action.name)
            button.setEnabled(action.enabled)

            if action.description is not None:
                button.setToolTip(action.description)

            button.clicked.connect(
                lambda _checked=False, action=action, entry_name=entry_name: self._execute_action(action, entry_name)
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
                f'Run "{action.name}" for "{entry_name}"?\n\nThis action may modify files.'
            )

            if not confirmed:
                return

        action.callback()

        if action.destructive:
            self.refresh()
