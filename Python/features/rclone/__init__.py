"""
rclone feature integration for Logistics.
"""

FEATURE_DESCRIPTION = 'Browse cloud storage and transfer files with rclone.'

FEATURE_NAME = 'rclone'
FEATURE_LABEL = 'rclone'


def desktop_session():
    """Resolve desktop credential ownership only at the desktop host boundary."""
    from . import session
    return session


def initialize() -> None:
    """Initialize the rclone feature."""

    from . import api
    api.initialize()


def get_contributions():
    """Return UI contributions provided by this feature."""

    from features.rclone.ui_contributions import get_contributions as _get_contributions
    return _get_contributions()


def register():
    """Unified declaration; get_contributions remains a compatibility entry point."""
    return get_contributions()
