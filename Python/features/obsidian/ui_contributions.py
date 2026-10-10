"""
UI contributions exposed by the Logistics Obsidian feature.
"""

from features.obsidian import detection
from features.contributions import Feature, FolderFeatureContribution, UIAction, WorkflowContribution
from models.folder_entry import FolderEntry
from commonUtils.filesystem.directories import Directory


def _is_available(entry: FolderEntry) -> bool:
    """Return whether the selected folder contains at least one Obsidian vault."""

    return entry.local is not None and detection.has_vault(entry.local)


def _get_actions(entry: FolderEntry) -> list[UIAction]:
    """Return one action for each Obsidian vault contained in this folder."""

    if entry.local is None:
        return []

    vaults = detection.get_vault_paths(entry.local)

    return [
        UIAction(
            name=f'Open "{vault.name}" Vault',
            description=f'Open Obsidian vault "{vault.name}".',
            workflow_id='obsidian_open_vault',
            workflow_data=vault
        )
        for vault in vaults
    ]


def _open_vault_workflow(data=None, parent=None):
    """Open the selected Obsidian vault."""

    if not isinstance(data, Directory):
        return False

    # Import locally to keep UI contribution discovery lightweight.
    from features.obsidian import actions
    return actions.open_vault(data)


def get_contributions() -> Feature:
    """Return UI contributions provided by Obsidian."""

    return Feature(
        id='obsidian', label='Obsidian',
        folder_features=[
            FolderFeatureContribution(
                name='Obsidian',
                is_available=_is_available,
                get_actions=_get_actions,
                order=20
            )
        ],
        workflows=[
            WorkflowContribution(
                workflow_id='obsidian_open_vault',
                handler=_open_vault_workflow
            )
        ]
    )
