"""
Merged folder discovery for the new Logistics UI.
"""

from features.rclone import configuration as rclone_configuration
from models import folder_discovery
from models.folder_entry import FolderEntry


def get_folder_entries() -> list[FolderEntry]:
    """
    Return logical folder entries merged from Server/Local and rclone.conf.

    Existing LocalFolder and RemoteFolder discovery remains unchanged for the
    legacy UI. This service is intended for the new UI.
    """

    local_folders = folder_discovery.get_local_folders()
    remote_names = rclone_configuration.get_rclone_remote_names()

    local_folders_by_name = {
        folder.name: folder
        for folder in local_folders
    }
    remote_name_set = set(remote_names)

    folder_names = sorted(
        set(local_folders_by_name) | remote_name_set,
        key=str.casefold
    )

    return [
        FolderEntry(
            name=folder_name,
            local=local_folders_by_name.get(folder_name),
            remote_name=folder_name if folder_name in remote_name_set else None
        )
        for folder_name in folder_names
    ]
