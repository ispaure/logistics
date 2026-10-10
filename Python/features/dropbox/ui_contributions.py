"""
UI contributions exposed by Dropbox.
"""

from features.contributions import (
    Feature,
    FolderFeatureContribution,
    LocalFolderSource,
    LocalFolderSourceContribution,
    UIAction,
    WorkflowContribution,
)
from features.dropbox import detection
from models.folder_entry import FolderEntry


def _get_local_sources() -> list[LocalFolderSource]:
    """Return one local Folders source for each configured Dropbox account."""

    roots = detection.get_dropbox_roots()
    multiple_accounts = len(roots) > 1
    sources = []

    for account_name, root_path in roots:
        display_name = f'Dropbox [{account_name.title()}]' if multiple_accounts else 'Dropbox'

        sources.append(
            LocalFolderSource(
                name=display_name,
                get_local_folders=lambda root_path=root_path:
                detection.get_dropbox_folders(root_path),
                context=root_path
            )
        )

    return sources


def _is_available(entry: FolderEntry) -> bool:
    """Offer Dropbox actions for local folders inside a detected Dropbox account."""

    if entry.local is None:
        return False

    folder_path = entry.local.path.resolve()
    return any(
        folder_path.is_relative_to(root_path.resolve())
        for _account_name, root_path in detection.get_dropbox_roots()
    )


def _get_actions(entry: FolderEntry) -> list[UIAction]:
    if not _is_available(entry):
        return []

    return [
        UIAction(
            name='Conflicting Copies...',
            description='Analyze or safely delete conflicting copies in this Dropbox folder.',
            workflow_id='debug_dropbox_conflicts',
            workflow_data=entry.local.path,
            destructive=True
        )
    ]


def _open_conflicts(data=None, parent=None):
    from features.dropbox.ui.dialogs import DropboxConflictsDialog

    dialog = DropboxConflictsDialog(initial_path=data, parent=parent)
    return dialog.exec()


def get_contributions() -> Feature:
    return Feature(
        id='dropbox', label='Dropbox',
        local_folder_sources=[
            LocalFolderSourceContribution(
                name='Dropbox',
                get_sources=_get_local_sources,
                order=10
            )
        ],
        folder_features=[
            FolderFeatureContribution(
                name='Dropbox',
                is_available=_is_available,
                get_actions=_get_actions,
                order=20
            )
        ],
        workflows=[
            WorkflowContribution(
                workflow_id='debug_dropbox_conflicts',
                handler=_open_conflicts
            )
        ]
    )
