"""
UI contributions exposed by the Logistics Plex feature.
"""

from pathlib import Path

from commonUtils.runtime.platform import OS, get_os

from features.contributions import (
    DebugActionContribution,
    Feature,
    FolderFeatureContribution,
    UIAction,
    WorkflowContribution,
)
from features.plex import database, detection
from features.rclone import configuration as rclone_configuration
from models.folder_entry import FolderEntry


def _has_manage_pms(entry: FolderEntry) -> bool:
    """Return whether this folder has a matching Plex -PMSDATA remote."""

    if entry.local is None:
        return False

    if get_os() not in (OS.WIN, OS.MAC, OS.LINUX):
        return False

    if entry.remote_source != 'rclone' or entry.remote_context is None:
        return False

    config_path = Path(entry.remote_context)
    remote_names = rclone_configuration.get_rclone_remote_names(config_path)
    return detection.has_pms_data_remote(entry.local, remote_names)


def _get_folder_actions(entry: FolderEntry) -> list[UIAction]:
    """Return Plex folder actions for the selected logical folder."""

    if entry.local is None:
        return []

    return [
        UIAction(
            name='Manage PMS...',
            workflow_id='plex_manage',
            workflow_data=entry,
            description='Back up or restore Plex Media Server data using the matching -PMSDATA remote.'
        )
    ]

def _open_manage_pms(data=None, parent=None):
    from features.plex.ui.manage_pms_dialog import PlexManagePMSDialog

    dialog = PlexManagePMSDialog(data, parent=parent)
    return dialog.exec()


def get_contributions() -> Feature:
    """Return UI contributions provided by Plex."""

    return Feature(
        id='plex', label='Plex', requires=('rclone',),
        folder_features=[
            FolderFeatureContribution(
                name='Plex',
                is_available=_has_manage_pms,
                get_actions=_get_folder_actions,
                order=40
            )
        ],
        workflows=[
            WorkflowContribution(
                workflow_id='plex_manage',
                handler=_open_manage_pms
            )
        ],
        debug_actions=[
            DebugActionContribution(
                name='Plex - Compare Databases...',
                callback=database.test_script,
                description='Select two Plex database copies and compare movies and episodes.'
            )
        ]
    )
