"""
UI contributions exposed by the Logistics Plex feature.
"""

from commonUtils.osUtils import OS, get_os

from features.contributions import (
    DebugActionContribution,
    FeatureContributions,
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

    if get_os() not in (OS.WIN, OS.MAC):
        return False

    remote_names = rclone_configuration.get_rclone_remote_names()
    return detection.has_pms_data_remote(entry.local, remote_names)


def _get_folder_actions(entry: FolderEntry) -> list[UIAction]:
    """Return Plex folder actions for the selected logical folder."""

    if entry.local is None:
        return []

    return [
        UIAction(
            name='Manage PMS...',
            workflow_id='plex_manage',
            workflow_data=entry.local,
            description='Back up or restore Plex Media Server data using the matching -PMSDATA remote.'
        )
    ]

def _open_manage_pms(data=None, parent=None):
    from features.plex.ui.manage_pms_dialog import PlexManagePMSDialog

    dialog = PlexManagePMSDialog(data, parent=parent)
    return dialog.exec()


def get_contributions() -> FeatureContributions:
    """Return UI contributions provided by Plex."""

    return FeatureContributions(
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
                name='PLEXDB - Parse Database Test',
                callback=database.test_script,
                description='Run the existing Plex database comparison/test script.'
            )
        ]
    )
