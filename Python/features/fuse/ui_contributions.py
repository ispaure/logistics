"""
Folder UI contribution exposed by the optional Logistics FUSE feature.
"""

from pathlib import Path

from features.contributions import (
    Feature,
    FolderFeatureContribution,
    UIAction,
)
from features.fuse import actions
from models.folder_entry import FolderEntry


def _get_config_path(entry: FolderEntry) -> Path | None:
    if entry.remote_source != 'rclone' or entry.remote_context is None:
        return None

    return Path(entry.remote_context)


def _is_available(entry: FolderEntry) -> bool:
    """
    Return whether this logical folder can expose the lazy mount action.

    This intentionally performs no FUSE, mount, filesystem-readiness, or network
    probing while the user browses the Folders tree.
    """

    return entry.remote_name is not None and _get_config_path(entry) is not None


def _get_actions(entry: FolderEntry) -> list[UIAction]:
    """Return the lazy mounted-folder action for one configured remote."""

    remote_name = entry.remote_name
    config_path = _get_config_path(entry)

    if remote_name is None or config_path is None:
        return []

    return [
        UIAction(
            name='Open Mount Folder',
            callback=lambda remote_name=remote_name, config_path=config_path:
            actions.mount_and_open_remote(remote_name, config_path),
            description=(
                'Open this rclone remote mount. If it is not already mounted, '
                'mount it on demand first.'
            )
        )
    ]


def get_contributions() -> Feature:
    """Return UI contributions provided by FUSE."""

    from . import initialize
    return Feature(
        id='fuse', label='FUSE', requires=('rclone',), initialize=initialize,
        folder_features=[
            FolderFeatureContribution(
                name='fuse',
                is_available=_is_available,
                get_actions=_get_actions,
                order=15
            )
        ]
    )
