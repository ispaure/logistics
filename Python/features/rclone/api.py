"""
Public API for the Logistics rclone feature.
"""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from . import configuration


def initialize() -> None:
    """Ensure the private rclone config directory is available."""

    configuration.ensure_rclone_config_dir()
