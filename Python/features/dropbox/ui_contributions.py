"""
UI contributions exposed by Dropbox.
"""

from features.contributions import (
    DebugActionContribution,
    FeatureContributions,
    LocalFolderSource,
    LocalFolderSourceContribution,
    WorkflowContribution,
)
from features.dropbox import detection


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


def _open_conflicts(data=None, parent=None):
    from features.dropbox.ui.dialogs import DropboxConflictsDialog

    dialog = DropboxConflictsDialog(initial_path=data, parent=parent)
    return dialog.exec()


def get_contributions() -> FeatureContributions:
    return FeatureContributions(
        local_folder_sources=[
            LocalFolderSourceContribution(
                name='Dropbox',
                get_sources=_get_local_sources,
                order=10
            )
        ],
        debug_actions=[
            DebugActionContribution(
                name='Conflicting Copies...',
                workflow_id='debug_dropbox_conflicts',
                destructive=True
            )
        ],
        workflows=[
            WorkflowContribution(
                workflow_id='debug_dropbox_conflicts',
                handler=_open_conflicts
            )
        ]
    )
