"""
UI contributions exposed by the Logistics Comics feature.
"""

from commonUtils.osUtils import OS, get_os

from features.comics import actions, detection
from features.contributions import FeatureContributions, FolderFeatureContribution, UIAction
from models.folder_entry import FolderEntry


def _is_available(entry: FolderEntry) -> bool:
    """Return whether the Comics feature has folder actions for this entry."""

    if entry.local is None:
        return False

    return (
        (get_os() == OS.WIN and detection.has_comic_rack(entry.local))
        or detection.has_yac_reader_library(entry.local)
    )


def _get_actions(entry: FolderEntry) -> list[UIAction]:
    """Return Comics actions available for a logical folder entry."""

    if entry.local is None:
        return []

    folder = entry.local
    ui_actions = []

    if get_os() == OS.WIN and detection.has_comic_rack(folder):
        ui_actions.append(
            UIAction(
                name='Open ComicRack',
                callback=lambda folder=folder: actions.open_comic_rack(folder)
            )
        )

    if detection.has_yac_reader_library(folder):
        ui_actions.append(
            UIAction(
                name='Open YACReaderLibrary',
                callback=lambda folder=folder: actions.open_yac_reader_library(folder)
            )
        )

    return ui_actions


def get_contributions() -> FeatureContributions:
    """Return UI contributions provided by Comics."""

    return FeatureContributions(
        folder_features=[
            FolderFeatureContribution(
                name='Comics',
                is_available=_is_available,
                get_actions=_get_actions
            )
        ]
    )
