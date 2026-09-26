"""
UI contributions exposed by the Logistics rclone feature.
"""

from features.contributions import FeatureContributions, FolderFeatureContribution, PageContribution, UIAction
from features.rclone import actions, fuse, mounts
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
    """Return on-demand FUSE mount/open actions for one rclone remote."""

    remote_name = entry.remote_name

    if remote_name is None:
        return []

    if not fuse.is_installed():
        dependency_name = fuse.get_dependency_name()
        installer_path = fuse.get_installer_path()

        if installer_path is not None:
            return [
                UIAction(
                    name=f'Install {dependency_name}...',
                    callback=fuse.launch_installer,
                    description=(
                        f'{dependency_name} is required before rclone can mount remote folders on this platform. '
                        f'Launch the bundled installer at {installer_path}.'
                    )
                )
            ]

        return [
            UIAction(
                name=f'{dependency_name} Required...',
                callback=fuse.launch_installer,
                description='FUSE support is required before this rclone remote can be mounted.'
            )
        ]

    is_mounted = mounts.is_remote_ready(remote_name)

    return [
        UIAction(
            name='Open Remote Folder' if is_mounted else 'Mount and Open Remote Folder',
            callback=lambda remote_name=remote_name: fuse.mount_and_open_remote(remote_name),
            description=(
                'Open the existing FUSE mount for this rclone remote.'
                if is_mounted
                else 'Mount only this rclone remote through FUSE, wait for it to become available, then open it.'
            )
        )
    ]


def get_contributions() -> FeatureContributions:
    """Return UI contributions provided by rclone."""

    return FeatureContributions(
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
