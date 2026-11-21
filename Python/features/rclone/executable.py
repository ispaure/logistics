"""Resolve pinned rclone builds without downloading during discovery/startup."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from pathlib import Path
from services import software


def get_rclone_path() -> Path:
    return software.get_software('rclone')[1]


def ensure_rclone() -> Path | None:
    """Offer the verified download immediately before a command needs rclone."""
    return software.ensure_software('rclone')
