"""
UI contributions exposed by the Logistics Calibre feature.
"""

from features.calibre import detection
from features.contributions import FeatureContributions, FolderFeatureContribution
from models.folder_entry import FolderEntry


def _is_available(entry: FolderEntry) -> bool:
    """Return whether the selected folder contains at least one Calibre library."""

    return entry.local is not None and detection.has_library(entry.local)


def _get_actions(_entry: FolderEntry):
    """Calibre uses a custom folder widget rather than flat folder actions."""

    return []


def _create_widget(entry: FolderEntry, parent=None):
    """Create the Calibre library selector/action section for a folder."""

    from features.calibre.folder_widget import CalibreFolderWidget

    return CalibreFolderWidget(entry, parent=parent)


def get_contributions() -> FeatureContributions:
    """Return UI contributions provided by Calibre."""

    return FeatureContributions(
        folder_features=[
            FolderFeatureContribution(
                name='Calibre',
                is_available=_is_available,
                get_actions=_get_actions,
                order=20,
                create_widget=_create_widget
            )
        ]
    )
