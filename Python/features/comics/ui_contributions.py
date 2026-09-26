"""
UI contributions exposed by the Logistics Comics feature.
"""

from commonUtils.osUtils import OS, get_os

from features.comics import actions, detection
from features.contributions import FeatureContributions, FolderFeatureContribution, UIAction, WorkflowContribution
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

def _open_dialog(dialog_name: str, data=None, parent=None):
    from features.comics.ui import dialogs

    dialog_type = getattr(dialogs, dialog_name)
    dialog = dialog_type(initial_path=data, parent=parent)
    return dialog.exec()


def _open_convert_cbr(data=None, parent=None):
    return _open_dialog('ConvertCbrDialog', data, parent)


def _open_author(data=None, parent=None):
    return _open_dialog('ComicAuthorDialog', data, parent)


def _open_series(data=None, parent=None):
    return _open_dialog('ComicSeriesDialog', data, parent)


def _open_individual_folders(data=None, parent=None):
    return _open_dialog('CbzIndividualFoldersDialog', data, parent)


def _open_compress_cbz(data=None, parent=None):
    return _open_dialog('CompressCbzDialog', data, parent)


def get_contributions() -> FeatureContributions:
    return FeatureContributions(
        folder_features=[
            FolderFeatureContribution(
                name='Comics',
                is_available=_is_available,
                get_actions=_get_actions,
                order=20
            )
        ],
        workflows=[
            WorkflowContribution('debug_comics_convert_cbr', _open_convert_cbr),
            WorkflowContribution('debug_comics_author', _open_author),
            WorkflowContribution('debug_comics_series', _open_series),
            WorkflowContribution('debug_comics_individual_folders', _open_individual_folders),
            WorkflowContribution('debug_comics_compress_cbz', _open_compress_cbz),
        ]
    )
