"""
Detection helpers for the Logistics Minecraft feature.
"""

from pathlib import Path

from commonUtils import marcUtils

from features.minecraft.server import MinecraftServerType


def get_server_root_path(server_type: MinecraftServerType) -> Path | None:
    """Return the configured root directory for a Minecraft server type."""

    marc_dropbox_path = marcUtils.get_marc_dropbox_root()

    if marc_dropbox_path is None or not Path(marc_dropbox_path).is_dir():
        return None

    match server_type:
        case MinecraftServerType.JAVA:
            return Path(marc_dropbox_path, 'Software', 'Server', 'Minecraft')

        case MinecraftServerType.BEDROCK:
            return Path(marc_dropbox_path, 'Software', 'Server', 'Minecraft (Bedrock)')

        case _:
            return None
