"""
rclone feature integration for Logistics.
"""

from . import api


FEATURE_NAME = 'rclone'
FEATURE_LABEL = 'rclone'


def initialize() -> None:
    """Initialize the rclone feature."""

    api.initialize()


def get_contributions():
    """Return UI contributions provided by this feature."""

    from features.rclone.ui_contributions import get_contributions as _get_contributions
    return _get_contributions()
