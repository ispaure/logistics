"""
UI contributions exposed by the Logistics Minecraft feature.
"""

from features.contributions import FeatureContributions, ServerProviderContribution, UIAction
from features.minecraft import detection, server


def _get_servers() -> list[server.MinecraftServer]:
    """Return all configured Minecraft servers."""

    minecraft_servers = []

    for server_type in (server.MinecraftServerType.JAVA, server.MinecraftServerType.BEDROCK):
        server_root = detection.get_server_root_path(server_type)
        minecraft_servers.extend(server.get_minecraft_server_lst(server_root))

    return minecraft_servers


def _get_server_actions(minecraft_server: server.MinecraftServer) -> list[UIAction]:
    """Return actions available for one Minecraft server."""

    return [
        UIAction(
            name='Launch Server',
            callback=minecraft_server.launch_server,
            enabled=minecraft_server.is_launchable()
        ),
        UIAction(
            name='Browse Folder',
            callback=minecraft_server.open_dir,
            enabled=minecraft_server.can_open_dir()
        ),
        UIAction(
            name='Open Wiki',
            callback=minecraft_server.open_wiki,
            enabled=minecraft_server.can_open_wiki()
        ),
        UIAction(
            name='server.properties',
            callback=minecraft_server.edit_properties,
            enabled=minecraft_server.can_edit_props()
        ),
    ]


def get_contributions() -> FeatureContributions:
    """Return UI contributions provided by Minecraft."""

    return FeatureContributions(
        server_providers=[
            ServerProviderContribution(
                name='Minecraft',
                get_servers=_get_servers,
                get_display_name=lambda minecraft_server: minecraft_server.name,
                get_group_name=lambda minecraft_server: minecraft_server.type.value,
                get_actions=_get_server_actions
            )
        ]
    )
