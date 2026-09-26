"""
FUSE-mounted rclone remote integration for Logistics.
"""

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
