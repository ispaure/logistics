"""
UI contributions exposed by the Logistics rclone feature.
"""

from features.contributions import FeatureContributions, FolderFeatureContribution, PageContribution, UIAction
from features.rclone import actions
from models.folder_entry import FolderEntry


def _is_available(entry: FolderEntry) -> bool:
    """Return whether rclone has actions for this logical folder."""

    return entry.has_remote


def _get_actions(entry: FolderEntry) -> list[UIAction]:
    """Return rclone actions available for a logical folder entry."""

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


def get_contributions() -> FeatureContributions:
    """Return UI contributions provided by rclone."""

    return FeatureContributions(
        folder_features=[
            FolderFeatureContribution(
                name='rclone',
                is_available=_is_available,
                get_actions=_get_actions,
                order=10
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
