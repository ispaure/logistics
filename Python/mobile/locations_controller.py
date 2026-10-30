"""Pinned-folder commands over explicit storage and navigation capabilities."""
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from .locations_ui import LocationsUI


@dataclass(frozen=True)
class LocationHost:
    private_root: Callable[[], Path]
    local_folder: Callable[[], str]
    remote_folder: Callable[[], Awaitable[tuple[str, str] | None]]
    local_status: Callable[[str], None]
    remote_status: Callable[[str], None]
    open_local: Callable[[str], Awaitable[None]]
    open_remote: Callable[[str, str], Awaitable[None]]
    show_locations: Callable[[], None]


class LocationsController(LocationsUI):
    def __init__(self, host: LocationHost):
        self.host = host
        self.location_error = ''
