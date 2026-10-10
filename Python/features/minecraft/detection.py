"""
Detection helpers for the Logistics Minecraft feature.
"""

from commonUtils.filesystem.directories import Directory
from models.local_folder import LocalFolder

from features.minecraft.server import MinecraftServer


MAX_SERVER_DEPTH = 3


def get_servers(folder: LocalFolder) -> list[MinecraftServer]:
    """Return Minecraft servers found up to three directory levels below a local folder."""

    # Directory.list_directories(depth=2) returns immediate children plus two
    # additional levels, which corresponds to paths 1-3 levels below folder.
    directories = Directory(folder.path).list_directories(depth=MAX_SERVER_DEPTH - 1)

    server_paths = [
        directory.path
        for directory in directories
        if (directory.path / 'server.properties').is_file()
    ]

    return [MinecraftServer(path) for path in server_paths]


def has_server(folder: LocalFolder) -> bool:
    """Return whether a local folder contains at least one Minecraft server."""

    return bool(get_servers(folder))
