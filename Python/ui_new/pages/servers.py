"""
Servers page for the replacement Logistics UI.
"""

from commonUtils import ui
from commonUtils.ui import pyside

from features import registry
from features.contributions import UIAction
from ui_new import workflows


class ServersPage(pyside.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.server_tree = pyside.QTreeWidget()
        self.server_tree.setHeaderHidden(True)
        self.server_tree.setMinimumWidth(220)
        self.server_tree.setMaximumWidth(340)

        self.detail_scroll = pyside.QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(pyside.QFrame.Shape.NoFrame)

        self.selected_server_key = None
        self._server_items = {}

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

        title_label = pyside.QLabel('Servers')
        title_font = title_label.font()
        title_font.setPointSize(title_font.pointSize() + 4)
        title_font.setBold(True)
        title_label.setFont(title_font)

        left_layout.addWidget(title_label)
        left_layout.addWidget(self.server_tree)

        splitter = pyside.QSplitter(pyside.Qt.Orientation.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(self.detail_scroll)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([270, 730])

        root_layout.addWidget(splitter)

    def _connect_signals(self):
        self.server_tree.currentItemChanged.connect(self._selection_changed)

    def refresh(self):
        """Refresh server providers while preserving the last real server selection."""

        providers = sorted(
            registry.get_server_providers(),
            key=lambda registered: (
                registered.contribution.order,
                registered.contribution.name.casefold()
            )
        )

        self.server_tree.clear()
        self._server_items = {}

        first_server_key = None

        for registered in providers:
            provider = registered.contribution

            provider_item = pyside.QTreeWidgetItem([provider.name])
            provider_font = provider_item.font(0)
            provider_font.setBold(True)
            provider_item.setFont(0, provider_font)
            self.server_tree.addTopLevelItem(provider_item)

            servers = sorted(
                provider.get_servers(),
                key=lambda server: provider.get_display_name(server).casefold()
            )

            group_items = {}

            for server in servers:
                group_name = provider.get_group_name(server) if provider.get_group_name is not None else None
                parent_item = provider_item

                if group_name:
                    group_item = group_items.get(group_name)

                    if group_item is None:
                        group_item = pyside.QTreeWidgetItem([group_name])
                        group_font = group_item.font(0)
                        group_font.setBold(True)
                        group_item.setFont(0, group_font)

                        provider_item.addChild(group_item)
                        group_items[group_name] = group_item

                    parent_item = group_item

                display_name = provider.get_display_name(server)
                server_item = pyside.QTreeWidgetItem([display_name])
                server_item.setData(
                    0,
                    pyside.Qt.ItemDataRole.UserRole,
                    (registered, server)
                )
                parent_item.addChild(server_item)

                server_key = self._get_server_key(registered, server)
                self._server_items[server_key] = server_item

                if first_server_key is None:
                    first_server_key = server_key

        self.server_tree.expandAll()

        if first_server_key is None:
            self.selected_server_key = None
            self._show_empty_state(providers)
            return

        selected_item = self._server_items.get(self.selected_server_key)

        if selected_item is None:
            self.selected_server_key = first_server_key
            selected_item = self._server_items[first_server_key]

        self.server_tree.setCurrentItem(selected_item)

    def _get_server_key(self, registered, server):
        provider = registered.contribution
        group_name = provider.get_group_name(server) if provider.get_group_name is not None else ''
        display_name = provider.get_display_name(server)

        return (
            registered.feature_name,
            provider.name,
            group_name,
            display_name
        )

    def _selection_changed(self, current, _previous):
        if current is None:
            return

        selection = current.data(0, pyside.Qt.ItemDataRole.UserRole)

        if selection is None:
            return

        registered, server = selection

        self.selected_server_key = self._get_server_key(registered, server)
        self._show_server(registered, server)

    def _show_empty_state(self, providers):
        widget = pyside.QWidget()
        layout = pyside.QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)

        if providers:
            message = 'Server providers are enabled, but no servers were discovered.'
        else:
            message = 'No enabled features currently provide servers.'

        label = pyside.QLabel(message)
        label.setWordWrap(True)

        layout.addWidget(label)
        layout.addStretch()

        self.detail_scroll.setWidget(widget)

    def _show_server(self, registered, server):
        provider = registered.contribution
        display_name = provider.get_display_name(server)

        widget = pyside.QWidget()
        layout = pyside.QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(14)

        title_label = pyside.QLabel(display_name)
        title_font = title_label.font()
        title_font.setPointSize(title_font.pointSize() + 7)
        title_font.setBold(True)
        title_label.setFont(title_font)

        layout.addWidget(title_label)
        layout.addWidget(self._create_details_section(registered, server))

        actions = provider.get_actions(server)

        if actions:
            layout.addWidget(self._create_action_section('Actions', actions, display_name))

        layout.addStretch()
        self.detail_scroll.setWidget(widget)

    def _create_details_section(self, registered, server):
        provider = registered.contribution

        group = pyside.QGroupBox('Server')
        layout = pyside.QFormLayout(group)

        provider_label = pyside.QLabel(provider.name)
        provider_label.setTextInteractionFlags(pyside.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addRow('Provider:', provider_label)

        if provider.get_group_name is not None:
            group_name = provider.get_group_name(server)

            if group_name:
                group_label = pyside.QLabel(group_name)
                group_label.setTextInteractionFlags(pyside.Qt.TextInteractionFlag.TextSelectableByMouse)
                layout.addRow('Group:', group_label)

        if provider.get_details is not None:
            for label, value in provider.get_details(server):
                value_label = pyside.QLabel(str(value))
                value_label.setWordWrap(True)
                value_label.setTextInteractionFlags(pyside.Qt.TextInteractionFlag.TextSelectableByMouse)
                layout.addRow(f'{label}:', value_label)

        return group

    def _create_action_section(self, title: str, actions: list[UIAction], server_name: str):
        group = pyside.QGroupBox(title)
        layout = pyside.QVBoxLayout(group)
        layout.setSpacing(8)

        for action in actions:
            button = pyside.QPushButton(action.name)
            button.setEnabled(action.enabled)

            if action.description is not None:
                button.setToolTip(action.description)

            button.clicked.connect(
                lambda _checked=False, action=action, server_name=server_name: self._execute_action(action, server_name)
            )

            layout.addWidget(button)

        return group

    def _execute_action(self, action: UIAction, server_name: str):
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
                f'Run "{action.name}" for "{server_name}"?\n\nThis action may modify files.'
            )

            if not confirmed:
                return

        action.callback()

        if action.destructive:
            self.refresh()
