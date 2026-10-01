"""
UI contributions exposed by the Logistics Minecraft feature.
"""

from features.contributions import FeatureContributions, FolderFeatureContribution
from features.minecraft import detection
from models.folder_entry import FolderEntry


def _is_available(entry: FolderEntry) -> bool:
    """Return whether the selected folder contains a Minecraft server within three levels."""

    return entry.local is not None and detection.has_server(entry.local)


def _get_actions(_entry: FolderEntry):
    """Minecraft uses a custom folder widget rather than flat folder actions."""

    return []


def _create_widget(entry: FolderEntry, parent=None):
    """Create the Minecraft server selector/action section for a folder."""

    from features.minecraft.folder_widget import MinecraftFolderWidget

    return MinecraftFolderWidget(entry, parent=parent)


def get_contributions() -> FeatureContributions:
    """Return UI contributions provided by Minecraft."""

    return FeatureContributions(
        folder_features=[
            FolderFeatureContribution(
                name='Minecraft',
                is_available=_is_available,
                get_actions=_get_actions,
                order=20,
                create_widget=_create_widget
            )
        ]
    )
