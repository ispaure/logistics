"""
Detection helpers for the Logistics Perforce feature.
"""

from pathlib import Path
import shutil

from commonUtils.configuration import legacy as configUtils

from models.local_folder import LocalFolder


FOLDER_CONFIG_NAME = "remoteConfig.ini"

PERFORCE_SECTION = "Perforce"
P4D_PATH_KEY = "p4d_path"
DATA_PATH_KEY = "data_path"
PORT_KEY = "port"


def get_p4d_path(folder: LocalFolder) -> str | None:
    """Return the configured P4D executable path for a LocalFolder."""

    config_path = Path(folder.path, FOLDER_CONFIG_NAME)

    if not config_path.is_file():
        return None

    return configUtils.config_section_map(config_path, PERFORCE_SECTION, P4D_PATH_KEY)


def get_data_path(folder: LocalFolder) -> str | None:
    """Return the configured Perforce data path for a LocalFolder."""

    config_path = Path(folder.path, FOLDER_CONFIG_NAME)

    if not config_path.is_file():
        return None

    return configUtils.config_section_map(config_path, PERFORCE_SECTION, DATA_PATH_KEY)


def get_port(folder: LocalFolder) -> str | None:
    """Return the configured Perforce server port for a LocalFolder."""

    config_path = Path(folder.path, FOLDER_CONFIG_NAME)

    if not config_path.is_file():
        return None

    return configUtils.config_section_map(config_path, PERFORCE_SECTION, PORT_KEY)


def get_server_id(folder: LocalFolder) -> str | None:
    """Read the server ID from the configured data directory."""

    data_path = get_data_path(folder)
    if not data_path:
        return None

    try:
        server_id = Path(folder.path, data_path, 'server.id').read_text(
            encoding='utf-8-sig'
        ).strip()
    except (OSError, UnicodeError):
        return None

    return server_id or None


def get_p4_client_path(folder: LocalFolder) -> str | None:
    """Prefer the folder's P4 client, falling back to the system PATH."""

    local_client = Path(folder.path, 'p4')
    if local_client.is_file():
        return str(local_client.resolve())
    return shutil.which('p4')


def has_p4d_server(folder: LocalFolder) -> bool:
    """Return whether the LocalFolder has the required P4D server configuration."""

    return get_p4d_path(folder) is not None and get_data_path(folder) is not None and get_port(folder) is not None
