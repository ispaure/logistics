"""
Public API for the Logistics rclone feature.
"""

from . import configuration


def initialize() -> None:
    """Ensure the private rclone config directory is available."""

    configuration.ensure_rclone_config_dir()
