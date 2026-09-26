"""
UI contributions exposed by the Logistics Calibre feature.
"""

from features.calibre import detection
from features.contributions import FeatureContributions, FolderFeatureContribution, UIAction
from models.folder_entry import FolderEntry


def _is_available(entry: FolderEntry) -> bool:
    """Return whether the selected folder contains at least one Calibre library."""

    return entry.local is not None and detection.has_library(entry.local)


def _get_actions(entry: FolderEntry) -> list[UIAction]:
    """Return Calibre actions available for a logical folder entry."""

    if entry.local is None:
        return []

    return [
        UIAction(
            name='Manage Libraries...',
            description='Browse and operate on Calibre libraries contained in this folder.',
            workflow_id='calibre_manage',
            workflow_data=entry.local
        )
    ]


def get_contributions() -> FeatureContributions:
    """Return UI contributions provided by Calibre."""

    return FeatureContributions(
        folder_features=[
            FolderFeatureContribution(
                name='Calibre',
                is_available=_is_available,
                get_actions=_get_actions,
                order=20
            )
        ]
    )
