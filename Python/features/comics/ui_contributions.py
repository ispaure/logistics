"""
UI contributions exposed by the Logistics Comics feature.
"""

from commonUtils.osUtils import OS, get_os

from features.comics import actions, detection
from features.contributions import FeatureContributions, FolderFeatureContribution, UIAction
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
    folder_path = folder.path

    ui_actions = []

    if get_os() == OS.WIN and detection.has_comic_rack(folder):
        ui_actions.append(
            UIAction(
                name='Open ComicRack',
                callback=lambda folder=folder: actions.open_comic_rack(folder),
                description='Open ComicRack using this folder’s configured ComicRack links.'
            )
        )

    if detection.has_yac_reader_library(folder):
        ui_actions.append(
            UIAction(
                name='Open YACReaderLibrary',
                callback=lambda folder=folder: actions.open_yac_reader_library(folder),
                description='Open YACReaderLibrary using this folder’s configured YACReaderLibrary INI.'
            )
        )

    ui_actions.extend([
        UIAction(
            name='Convert CBR to CBZ...',
            workflow_id='debug_comics_convert_cbr',
            description='Open the batch conversion dialog.'
        ),
        UIAction(
            name='Set ComicInfo Author...',
            workflow_id='debug_comics_author',
            description='Open the author replacement dialog.'
        ),
        UIAction(
            name='Set ComicInfo Series...',
            workflow_id='debug_comics_series',
            description='Open the series replacement dialog.'
        ),
        UIAction(
            name='Move CBZ into Individual Folders...',
            workflow_id='debug_comics_individual_folders',
            description='Open the CBZ organization dialog.'
        ),
        UIAction(
            name='Compress CBZ...',
            workflow_id='debug_comics_compress_cbz',
            workflow_data=folder_path,
            description='Open the CBZ compression dialog with this folder pre-selected.'
        ),
    ])

    return ui_actions


def get_contributions() -> FeatureContributions:
    return FeatureContributions(
        folder_features=[
            FolderFeatureContribution(
                name='Comics',
                is_available=_is_available,
                get_actions=_get_actions,
                order=20
            )
        ]
    )
