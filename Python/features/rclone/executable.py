"""Resolve pinned rclone builds without downloading during discovery/startup."""
from pathlib import Path
from services import software


def get_rclone_path() -> Path:
    return software.get_software('rclone')[1]


def ensure_rclone() -> Path | None:
    """Offer the verified download immediately before a command needs rclone."""
    return software.ensure_software('rclone')
