"""
Merged folder discovery for the new Logistics UI.
"""

import config

from commonUtils import configUtils
from features.rclone import configuration as rclone_configuration
from models import folder_discovery
from models.folder_entry import FolderEntry


def _get_excluded_remote_names() -> set[str]:
    """
    Return configured rclone remote names that should not appear as logical folders.

    Names are stored in configFile.ini as one comma-separated value and compared
    case-insensitively.
    """

    excluded_names = configUtils.config_section_map(
        config.get_config_file_path(),
        'Folders',
        'excluded_remote_names'
    )

    if not excluded_names:
        return set()

    return {
        name.strip().casefold()
        for name in excluded_names.split(',')
        if name.strip()
    }


def get_folder_entries() -> list[FolderEntry]:
    """
    Return logical folder entries merged from Server/Local and rclone.conf.

    Existing LocalFolder and RemoteFolder discovery remains unchanged for the
    legacy UI. Remote names listed in [Folders] excluded_remote_names are omitted
    from the merged remote set, but a matching local folder can still appear.
    """

    local_folders = folder_discovery.get_local_folders()
    remote_names = rclone_configuration.get_rclone_remote_names()
    excluded_remote_names = _get_excluded_remote_names()

    local_folders_by_name = {
        folder.name: folder
        for folder in local_folders
    }

    remote_names_by_casefold = {
        remote_name.casefold(): remote_name
        for remote_name in remote_names
        if remote_name.casefold() not in excluded_remote_names
    }

    folder_names = sorted(
        set(local_folders_by_name) | set(remote_names_by_casefold.values()),
        key=str.casefold
    )

    return [
        FolderEntry(
            name=folder_name,
            local=local_folders_by_name.get(folder_name),
            remote_name=remote_names_by_casefold.get(folder_name.casefold())
        )
        for folder_name in folder_names
    ]
