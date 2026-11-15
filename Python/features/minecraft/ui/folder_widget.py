"""Folder-detail UI for Minecraft servers discovered inside a Logistics folder."""

from commonUtils.ui import pyside
from commonUtils.ui.pyside.selection_details import SelectionDetails

from features.minecraft import detection
from features.minecraft.server import MinecraftServer, MinecraftServerType
from models.folder_entry import FolderEntry


class MinecraftFolderWidget(SelectionDetails):
    """Display discovered Minecraft servers and actions for the selected server."""

    def __init__(self, entry: FolderEntry, parent=None):
        edition_tabs = pyside.QTabBar()
        edition_tabs.setExpanding(False)
        edition_tabs.setAccessibleName('Minecraft server edition')
        for server_type in (MinecraftServerType.JAVA, MinecraftServerType.BEDROCK):
            index = edition_tabs.addTab(server_type.value)
            edition_tabs.setTabData(index, server_type)

        super().__init__('Minecraft', self._show_server, parent, list_header=edition_tabs)
        self.edition_tabs = edition_tabs
        self.servers = detection.get_servers(entry.local) if entry.local is not None else []
        available_editions = {server.type for server in self.servers}
        if MinecraftServerType.JAVA not in available_editions and MinecraftServerType.BEDROCK in available_editions:
            edition_tabs.setCurrentIndex(1)
        edition_tabs.currentChanged.connect(self._refresh_server_list)
        self._refresh_server_list()

    def _refresh_server_list(self):
        edition = self.edition_tabs.tabData(self.edition_tabs.currentIndex())
        self.set_entries((server for server in self.servers if server.type == edition),
                         label=lambda server: server.name)

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

        self.add_detail_action(
            'Launch Server',
            minecraft_server.launch_server,
            enabled=minecraft_server.is_launchable(),
            tooltip='Launch this Minecraft server.'
        )
        self.add_detail_action(
            'Open Folder',
            minecraft_server.open_dir,
            enabled=minecraft_server.can_open_dir(),
            tooltip='Open the server directory.'
        )
        self.add_detail_action(
            'server.properties',
            minecraft_server.edit_properties,
            enabled=minecraft_server.can_edit_props(),
            tooltip='Open server.properties in the default text editor.'
        )
        self.add_detail_action(
            'Open Wiki',
            minecraft_server.open_wiki,
            enabled=minecraft_server.can_open_wiki(),
            tooltip='Open the configured documentation or wiki URL.'
        )
