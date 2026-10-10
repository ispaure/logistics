"""
UI contributions exposed by the Logistics Perforce feature.
"""

from commonUtils.osUtils import OS, get_os

from features.contributions import Feature, FolderFeatureContribution, UIAction
from features.perforce import actions, detection
from models.folder_entry import FolderEntry


def _is_available(entry: FolderEntry) -> bool:
    """Return whether this logical folder contains a configured P4D server."""

    return entry.local is not None and detection.has_p4d_server(entry.local)


def _get_actions(entry: FolderEntry) -> list[UIAction]:
    """Return Perforce actions available for a logical folder entry."""

    if entry.local is None:
        return []

    folder = entry.local

    p4d_path = detection.get_p4d_path(folder)
    data_path = detection.get_data_path(folder)
    port = detection.get_port(folder)
    server_id = detection.get_server_id(folder)
    name = f'Launch P4D {server_id.upper()} (Port: {port})' if server_id else f'Launch P4D (Port: {port})'

    description = (
        f'Launch P4D using "{p4d_path}" with data path "{data_path}" '
        f'on port {port}. Linux only.'
    )

    return [
        UIAction(
            name=name,
            callback=lambda folder=folder: actions.launch_server(folder),
            description=description,
            enabled=get_os() == OS.LINUX
        ),
        UIAction(
            name=f'Open P4 Console (Port: {port})',
            callback=lambda folder=folder: actions.open_console(folder),
            description='Open a terminal for this server. Type p4 commands without the path or port. Linux only; requires a local or installed p4 client.',
            enabled=get_os() == OS.LINUX and detection.get_p4_client_path(folder) is not None
        )
    ]


def get_contributions() -> Feature:
    """Return UI contributions provided by Perforce."""

    return Feature(
        id='perforce', label='Perforce',
        folder_features=[
            FolderFeatureContribution(
                name='Perforce',
                is_available=_is_available,
                get_actions=_get_actions,
                order=30
            )
        ]
    )
