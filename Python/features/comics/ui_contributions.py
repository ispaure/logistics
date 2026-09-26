"""
UI contributions exposed by the Logistics Comics feature.
"""

from commonUtils.osUtils import OS, get_os

from features.comics import actions, detection
from features.contributions import (
    DebugActionContribution,
    FeatureContributions,
    FolderFeatureContribution,
    UIAction,
)
from models.folder_entry import FolderEntry


def _is_available(entry: FolderEntry) -> bool:
    if entry.local is None:
        return False

    return (
        (get_os() == OS.WIN and detection.has_comic_rack(entry.local))
        or detection.has_yac_reader_library(entry.local)
    )


def _get_actions(entry: FolderEntry) -> list[UIAction]:
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
    return FeatureContributions(
        folder_features=[
            FolderFeatureContribution(
                name='Comics',
                is_available=_is_available,
                get_actions=_get_actions
            )
        ],
        debug_actions=[
            DebugActionContribution(
                name='Batch Convert CBR to CBZ...',
                workflow_id='debug_comics_convert_cbr',
                destructive=True,
                order=10
            ),
            DebugActionContribution(
                name='ComicInfo.xml - Set Author...',
                workflow_id='debug_comics_author',
                destructive=True,
                order=20
            ),
            DebugActionContribution(
                name='ComicInfo.xml - Set Series...',
                workflow_id='debug_comics_series',
                destructive=True,
                order=30
            ),
            DebugActionContribution(
                name='Move CBZ into Individual Folders...',
                workflow_id='debug_comics_individual_folders',
                destructive=True,
                order=40
            ),
            DebugActionContribution(
                name='Batch Compress CBZ...',
                workflow_id='debug_comics_compress_cbz',
                destructive=True,
                order=50
            ),
        ]
    )
