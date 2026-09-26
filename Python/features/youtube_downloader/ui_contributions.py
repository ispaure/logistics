"""
UI contributions exposed by the Logistics YouTube Downloader feature.
"""

from features.contributions import FeatureContributions, FolderFeatureContribution, UIAction, WorkflowContribution
from features.youtube_downloader import detection
from models.folder_entry import FolderEntry


def _is_available(entry: FolderEntry) -> bool:
    """Return whether this local folder has YouTube Downloader configuration."""

    return entry.local is not None and detection.has_config(entry.local)


def _get_actions(entry: FolderEntry) -> list[UIAction]:
    """Return YouTube Downloader actions available for a logical folder entry."""

    if entry.local is None:
        return []

    return [
        UIAction(
            name='YouTube Downloader...',
            workflow_id='youtube_downloader_manage',
            workflow_data=entry,
            description='Download configured channels/playlists and manage YouTube-specific remote sync operations.'
        )
    ]

def _open_manage(data=None, parent=None):
    from features.youtube_downloader.ui.dialog import YouTubeDownloaderDialog

    dialog = YouTubeDownloaderDialog(data, parent=parent)
    return dialog.exec()


def get_contributions() -> FeatureContributions:
    """Return UI contributions provided by YouTube Downloader."""

    return FeatureContributions(
        folder_features=[
            FolderFeatureContribution(
                name='YouTube Downloader',
                is_available=_is_available,
                get_actions=_get_actions,
                order=50
            )
        ],
        workflows=[
            WorkflowContribution(
                workflow_id='youtube_downloader_manage',
                handler=_open_manage
            )
        ]
    )
