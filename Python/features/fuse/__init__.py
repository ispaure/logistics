"""
FUSE-mounted rclone remote integration for Logistics.
"""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

FEATURE_DESCRIPTION = 'Mount rclone remotes as local folders.'

FEATURE_NAME = 'fuse'
FEATURE_LABEL = 'FUSE'
FEATURE_DEPENDENCIES = ('rclone',)


def initialize() -> None:
    """Initialize local mount housekeeping without mounting any remotes."""

    from features.fuse import mounts
    mounts.initialize()


def get_contributions():
    """Return UI contributions provided by this feature."""

    from features.fuse.ui_contributions import get_contributions as _get_contributions
    return _get_contributions()


def register():
    """Unified declaration; get_contributions remains a compatibility entry point."""
    return get_contributions()
