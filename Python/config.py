from pathlib import Path
from typing import Optional

from commonUtils import configUtils, fileUtils, marcUtils
from commonUtils.osUtils import OS, get_os


def get_config_file_path() -> Path:
    """Return the path to the Logistics configuration file."""

    return Path(__file__).resolve().parent / 'configFile.ini'


class LogisticsConfig:
    """
    Stores the Logistics configuration.
    """

    def __init__(self):
        config_file_path = get_config_file_path()
        user_home_dir = fileUtils.get_user_home_dir()
        current_os = get_os()

        # Logistics paths
        self.path_logistics: Path = Path(__file__).resolve().parent.parent
        self.path_logistics_scripts: Path = self.path_logistics / 'Scripts'

        # Server path
        match current_os:
            case OS.WIN:
                server_sub_path = configUtils.config_section_map(config_file_path, 'DirectoryStructure', 'server_path_win32')
            case OS.MAC:
                server_sub_path = configUtils.config_section_map(config_file_path, 'DirectoryStructure', 'server_path_macos')
            case OS.LINUX:
                server_sub_path = configUtils.config_section_map(config_file_path, 'DirectoryStructure', 'server_path_linux')
            case _:
                raise RuntimeError(f'Unsupported platform: {current_os}')

        self.server_path: Path = Path(user_home_dir, server_sub_path)

        # External Logistics resources
        marc_dropbox_path = marcUtils.get_marc_dropbox_root()
        local_software_path = self.path_logistics / 'Software'
        local_credentials_path = self.path_logistics / 'RemoteCredentials'

        if local_software_path.is_dir() and local_credentials_path.is_dir():
            self.path_logistics_software: Path = local_software_path
            self.path_logistics_remote_cred: Path = local_credentials_path
        elif marc_dropbox_path is not None and Path(marc_dropbox_path).is_dir():
            self.path_logistics_software: Path = Path(marc_dropbox_path, 'Software', 'GIT', 'logistics', 'Software')
            self.path_logistics_remote_cred: Path = Path(marc_dropbox_path, 'Software', 'GIT', 'logistics', 'RemoteCredentials')
        else:
            self.path_logistics_software: Path = self.server_path / 'Logistics' / 'Software'
            self.path_logistics_remote_cred: Path = self.server_path / 'Logistics' / 'RemoteCredentials'

        # Platform-specific software directories
        self.path_logistics_software_win: Path = self.path_logistics_software / 'Windows'
        self.path_logistics_software_mac: Path = self.path_logistics_software / 'macOS'
        self.path_logistics_software_linux: Path = self.path_logistics_software / 'Linux'
        self.path_logistics_software_general: Path = self.path_logistics_software / 'General'

        # General paths
        self.temp_path: Path = self.path_logistics / 'temp'

        remote_network_mount_sub_path = configUtils.config_section_map(
            config_file_path, 'DirectoryStructure', 'remote_network_mount_sub_path'
        )
        remote_local_sub_path = configUtils.config_section_map(
            config_file_path, 'DirectoryStructure', 'remote_local_sub_path'
        )

        self.path_remote_network_mount: Path = self.server_path / remote_network_mount_sub_path
        self.path_remote_local: Path = self.server_path / remote_local_sub_path

        # Minecraft server paths
        if marc_dropbox_path is not None and Path(marc_dropbox_path).is_dir():
            self.path_minecraft_servers_java: Optional[Path] = Path(marc_dropbox_path, 'Software', 'Server', 'Minecraft')
            self.path_minecraft_servers_bedrock: Optional[Path] = Path(
                marc_dropbox_path, 'Software', 'Server', 'Minecraft (Bedrock)'
            )
        else:
            self.path_minecraft_servers_java = None
            self.path_minecraft_servers_bedrock = None
