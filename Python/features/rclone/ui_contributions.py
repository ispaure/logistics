"""
UI contributions exposed by the Logistics rclone feature.
"""

from pathlib import Path

from features.contributions import (
    FeatureContributions,
    FolderFeatureContribution,
    PageContribution,
    RemoteFolderSource,
    RemoteFolderSourceContribution,
    UIAction,
    WorkflowContribution,
)
from features.rclone import actions, configuration, credentials
from models.folder_entry import FolderEntry


def _get_config_path(entry: FolderEntry) -> Path | None:
    """Return the selected rclone config carried by this folder entry."""

    if entry.remote_source != 'rclone':
        return None

    if entry.remote_context is None:
        return None

    return Path(entry.remote_context)


def _is_available(entry: FolderEntry) -> bool:
    """Return whether rclone has sync actions for this logical folder."""

    return entry.has_remote and _get_config_path(entry) is not None


def _get_actions(entry: FolderEntry) -> list[UIAction]:
    """Return rclone sync actions available for a logical folder entry."""

    config_path = _get_config_path(entry)

    if config_path is None:
        return []

    ui_actions = []

    if entry.local is not None and entry.remote_name is not None:
        ui_actions.append(
            UIAction(
                name='Push...',
                description=(
                    'Configure and push local data to the matching rclone remote.'
                ),
                workflow_id='rclone_push',
                workflow_data=entry
            )
        )

    if entry.remote_name is not None:
        ui_actions.append(
            UIAction(
                name='Pull',
                callback=lambda remote_name=entry.remote_name, config_path=config_path:
                actions.pull_remote(remote_name, config_path),
                description=(
                    'Sync the rclone remote into its matching local folder.'
                ),
                destructive=True
            )
        )

    return ui_actions


def _get_remote_sources() -> list[RemoteFolderSource]:
    """Return one Folders source for every loaded credential config."""

    sources = []

    for config_path in credentials.get_loaded_credential_config_paths():
        sources.append(
            RemoteFolderSource(
                name=f'rclone [{config_path.stem}]',
                get_remote_names=lambda config_path=config_path:
                configuration.get_rclone_remote_names(config_path),
                context=config_path
            )
        )

    return sources


def _open_push_workflow(data=None, parent=None):
    from features.rclone.ui.push_dialog import RclonePushDialog

    dialog = RclonePushDialog(data, parent=parent)
    return dialog.exec()


def _create_page(parent=None):
    from features.rclone.ui.page import RclonePage

    return RclonePage(parent=parent)


def get_contributions() -> FeatureContributions:
    """Return UI contributions provided by rclone."""

    return FeatureContributions(
        remote_folder_sources=[
            RemoteFolderSourceContribution(
                name='rclone',
                get_sources=_get_remote_sources,
                order=10
            )
        ],
        folder_features=[
            FolderFeatureContribution(
                name='rclone',
                is_available=_is_available,
                get_actions=_get_actions,
                order=10
            )
        ],
        workflows=[
            WorkflowContribution(
                workflow_id='rclone_push',
                handler=_open_push_workflow
            )
        ],
        pages=[
            PageContribution(
                name='rclone',
                page_id='rclone',
                create_page=_create_page,
                order=10
            )
        ]
    )
