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

        self.folder_list = pyside.QListWidget()
        self.folder_list.setMinimumWidth(220)
        self.folder_list.setMaximumWidth(320)

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
        left_layout.addWidget(self.folder_list)

        splitter = pyside.QSplitter(pyside.Qt.Orientation.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(self.detail_scroll)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([250, 750])

        root_layout.addWidget(splitter)

    def _connect_signals(self):
        self.folder_list.currentItemChanged.connect(self._selection_changed)

    def refresh(self):
        """Refresh merged folder discovery while preserving the current selection when possible."""

        current_item = self.folder_list.currentItem()
        selected_name = current_item.text() if current_item is not None else None

        self.folder_list.clear()

        entries = get_folder_entries()

        for entry in entries:
            item = pyside.QListWidgetItem(entry.name)
            item.setData(pyside.Qt.ItemDataRole.UserRole, entry)
            self.folder_list.addItem(item)

        if not entries:
            self._show_empty_state()
            return

        target_row = 0

        if selected_name is not None:
            for row in range(self.folder_list.count()):
                if self.folder_list.item(row).text() == selected_name:
                    target_row = row
                    break

        self.folder_list.setCurrentRow(target_row)

    def _selection_changed(self, current, _previous):
        if current is None:
            self._show_empty_state()
            return

        entry = current.data(pyside.Qt.ItemDataRole.UserRole)
        self._show_entry(entry)

    def _show_empty_state(self):
        widget = pyside.QWidget()
        layout = pyside.QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)

        label = pyside.QLabel('No folders were found in Server/Local or rclone.conf.')
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
