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
            description='Launch this Minecraft server.',
            enabled=minecraft_server.is_launchable()
        ),
        UIAction(
            name='Open Folder',
            callback=minecraft_server.open_dir,
            description='Open the server directory.',
            enabled=minecraft_server.can_open_dir()
        ),
        UIAction(
            name='server.properties',
            callback=minecraft_server.edit_properties,
            description='Open server.properties in the default text editor.',
            enabled=minecraft_server.can_edit_props()
        ),
        UIAction(
            name='Open Wiki',
            callback=minecraft_server.open_wiki,
            description='Open the configured documentation or wiki URL.',
            enabled=minecraft_server.can_open_wiki()
        ),
    ]


def _get_server_details(minecraft_server: server.MinecraftServer) -> list[tuple[str, str]]:
    """Return display details for one Minecraft server."""

    return [
        ('Type', minecraft_server.type.value),
        ('Path', str(minecraft_server.path)),
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
                get_details=_get_server_details,
                get_actions=_get_server_actions
            )
        ]
    )
