"""Pinned-folder commands over explicit storage and navigation capabilities."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

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
