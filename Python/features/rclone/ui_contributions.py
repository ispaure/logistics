"""
UI contributions exposed by the Logistics rclone feature.
"""

from features.contributions import (
    FeatureContributions,
    FolderFeatureContribution,
    PageContribution,
    RemoteFolderSourceContribution,
    UIAction,
)
from features.rclone import actions, configuration, fuse
from models.folder_entry import FolderEntry


def _is_available(entry: FolderEntry) -> bool:
    """Return whether rclone has sync actions for this logical folder."""

    return entry.has_remote


def _get_actions(entry: FolderEntry) -> list[UIAction]:
    """Return rclone sync actions available for a logical folder entry."""

    ui_actions = []

    if entry.local is not None and entry.remote_name is not None:
        ui_actions.append(
            UIAction(
                name='Push...',
                description='Configure and push local data to the matching rclone remote.',
                workflow_id='rclone_push',
                workflow_data=entry
            )
        )

    if entry.remote_name is not None:
        ui_actions.append(
            UIAction(
                name='Pull',
                callback=lambda remote_name=entry.remote_name: actions.pull_remote(remote_name),
                description='Sync the rclone remote into its matching local folder.',
                destructive=True
            )
        )

    return ui_actions


def _is_fuse_available(entry: FolderEntry) -> bool:
    """Return whether this logical folder has a remote that can be mounted through FUSE."""

    return entry.remote_name is not None


def _get_fuse_actions(entry: FolderEntry) -> list[UIAction]:
    """
    Return the lazy FUSE action for one rclone remote.

    Folder selection must not probe the mount or perform any remote/network work.
    FUSE availability, existing mount state, mounting, and readiness are resolved
    only when the user explicitly clicks the action.
    """

    remote_name = entry.remote_name

    if remote_name is None:
        return []

    return [
        UIAction(
            name='Open Mount Folder',
            callback=lambda remote_name=remote_name: fuse.mount_and_open_remote(remote_name),
            description=(
                'Open this rclone remote mount. If it is not already mounted, '
                'mount it on demand first.'
            )
        )
    ]


def get_contributions() -> FeatureContributions:
    """Return UI contributions provided by rclone."""

    return FeatureContributions(
        remote_folder_sources=[
            RemoteFolderSourceContribution(
                name='rclone',
                get_remote_names=configuration.get_rclone_remote_names,
                order=10
            )
        ],
        folder_features=[
            FolderFeatureContribution(
                name='rclone',
                is_available=_is_available,
                get_actions=_get_actions,
                order=10
            ),
            FolderFeatureContribution(
                name='fuse',
                is_available=_is_fuse_available,
                get_actions=_get_fuse_actions,
                order=15
            )
        ],
        pages=[
            PageContribution(
                name='rclone',
                page_id='rclone',
                order=10
            )
        ]
    )
