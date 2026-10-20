"""Folder-detail UI for Minecraft servers discovered inside a Logistics folder."""

from commonUtils.ui import pyside

from features.minecraft import detection
from features.minecraft.server import MinecraftServer, MinecraftServerType
from models.folder_entry import FolderEntry


class MinecraftFolderWidget(pyside.QGroupBox):
    """Display discovered Minecraft servers and actions for the selected server."""

    def __init__(self, entry: FolderEntry, parent=None):
        super().__init__('Minecraft', parent)

        self.servers = detection.get_servers(entry.local) if entry.local is not None else []
        self.filtered_servers: list[MinecraftServer] = []

        self.server_type_tabs = pyside.QTabBar()
        self.server_type_tabs.setExpanding(False)
        self.server_type_tabs.setAccessibleName('Minecraft server edition')
        for server_type in (MinecraftServerType.JAVA, MinecraftServerType.BEDROCK):
            index = self.server_type_tabs.addTab(server_type.value)
            self.server_type_tabs.setTabData(index, server_type)

        self.server_list = pyside.QListWidget()
        self.server_list.setMinimumWidth(150)
        self.server_list.setMaximumWidth(240)

        self.details_widget = pyside.QWidget()
        self.details_layout = pyside.QVBoxLayout(self.details_widget)
        self.details_layout.setContentsMargins(0, 0, 0, 0)
        self.details_layout.setSpacing(8)

        self._build_layout()

        self.server_type_tabs.currentChanged.connect(self._server_type_changed)
        self.server_list.currentRowChanged.connect(self._server_changed)

        self._select_initial_server_type()
        self._populate_servers()

    def _build_layout(self):
        layout = pyside.QHBoxLayout(self)
        layout.setSpacing(12)

        server_panel = pyside.QWidget()
        server_panel_layout = pyside.QVBoxLayout(server_panel)
        server_panel_layout.setContentsMargins(0, 0, 0, 0)
        server_panel_layout.setSpacing(6)
        server_panel_layout.addWidget(self.server_type_tabs)
        server_panel_layout.addWidget(self.server_list, 1)

        layout.addWidget(server_panel)
        layout.addWidget(self.details_widget, 1)

    def _select_initial_server_type(self):
        """Prefer Java when available, otherwise select Bedrock."""

        has_java = any(server.type == MinecraftServerType.JAVA for server in self.servers)
        has_bedrock = any(server.type == MinecraftServerType.BEDROCK for server in self.servers)

        if has_java:
            self.server_type_tabs.setCurrentIndex(0)
        elif has_bedrock:
            self.server_type_tabs.setCurrentIndex(1)

    def _server_type_changed(self, _index: int):
        self._populate_servers()

    def _populate_servers(self):
        self.server_list.clear()
        self._clear_details()

        selected_type = self.server_type_tabs.tabData(self.server_type_tabs.currentIndex())
        self.filtered_servers = [
            server
            for server in self.servers
            if server.type == selected_type
        ]

        for minecraft_server in self.filtered_servers:
            self.server_list.addItem(minecraft_server.name)

        if self.filtered_servers:
            self.server_list.setCurrentRow(0)

    def _server_changed(self, row: int):
        self._clear_details()

        if row < 0 or row >= len(self.filtered_servers):
            return

        self._show_server(self.filtered_servers[row])

    def _clear_details(self):
        while self.details_layout.count():
            item = self.details_layout.takeAt(0)
            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

    def _show_server(self, minecraft_server: MinecraftServer):
        title = pyside.QLabel(minecraft_server.name)
        title_font = title.font()
        title_font.setBold(True)
        title.setFont(title_font)
        self.details_layout.addWidget(title)

        path_label = pyside.QLabel(str(minecraft_server.path))
        path_label.setWordWrap(True)
        path_label.setTextInteractionFlags(pyside.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.details_layout.addWidget(path_label)

        self._add_action_button(
            'Launch Server',
            minecraft_server.launch_server,
            minecraft_server.is_launchable(),
            'Launch this Minecraft server.'
        )
        self._add_action_button(
            'Open Folder',
            minecraft_server.open_dir,
            minecraft_server.can_open_dir(),
            'Open the server directory.'
        )
        self._add_action_button(
            'server.properties',
            minecraft_server.edit_properties,
            minecraft_server.can_edit_props(),
            'Open server.properties in the default text editor.'
        )
        self._add_action_button(
            'Open Wiki',
            minecraft_server.open_wiki,
            minecraft_server.can_open_wiki(),
            'Open the configured documentation or wiki URL.'
        )

        self.details_layout.addStretch()

    def _add_action_button(self, name, callback, enabled: bool, tooltip: str):
        button = pyside.QPushButton(name)
        button.setEnabled(enabled)
        button.setToolTip(tooltip)
        button.clicked.connect(lambda _checked=False, callback=callback: callback())
        self.details_layout.addWidget(button)
