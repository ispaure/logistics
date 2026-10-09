from configparser import ConfigParser
from pathlib import Path
from commonUtils import configUtils, fileUtils
from commonUtils.osUtils import OS, get_os
from commonUtils.storage import temporary_directory


def get_config_file_path() -> Path:
    """Return the path to the Logistics configuration file."""

    return Path(__file__).resolve().parent / 'configFile.ini'


class LogisticsConfig:
    """
    Stores shared Logistics configuration.

    Feature-specific settings belong in the owning feature package rather than
    in the root configFile.ini.
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

        # Local/private resources default to the checkout and are independent.
        # Explicit overrides can still point either directory at Dropbox.
        resources = ConfigParser(interpolation=None)
        resources.read(config_file_path, encoding='utf-8-sig')

        def resource_path(key, default):
            value = resources.get('Resources', key, fallback=default).strip() or default
            path = Path(value).expanduser()
            if not path.is_absolute():
                path = self.path_logistics / path
            path.mkdir(parents=True, exist_ok=True)
            return path

        self.path_logistics_software = resource_path('software_path', 'Software')
        self.path_logistics_remote_cred = resource_path('credentials_path', 'RemoteCredentials')

        # Platform-specific software directories
        self.path_logistics_software_win: Path = self.path_logistics_software / 'Windows'
        self.path_logistics_software_mac: Path = self.path_logistics_software / 'macOS'
        self.path_logistics_software_linux: Path = self.path_logistics_software / 'Linux'
        self.path_logistics_software_general: Path = self.path_logistics_software / 'General'

        # General paths
        self.temp_path: Path = temporary_directory(create=False)

        remote_network_mount_sub_path = configUtils.config_section_map(
            config_file_path, 'DirectoryStructure', 'remote_network_mount_sub_path'
        )
        remote_local_sub_path = configUtils.config_section_map(
            config_file_path, 'DirectoryStructure', 'remote_local_sub_path'
        )

        self.path_remote_network_mount: Path = self.server_path / remote_network_mount_sub_path
        self.path_remote_local: Path = self.server_path / remote_local_sub_path

