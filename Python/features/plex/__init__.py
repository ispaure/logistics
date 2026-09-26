"""
Plex feature integration for Logistics.
"""

FEATURE_NAME = 'plex'
FEATURE_LABEL = 'Plex'
FEATURE_DEPENDENCIES = ('rclone',)


def get_contributions():
    """Return UI contributions provided by this feature."""

    from features.plex.ui_contributions import get_contributions as _get_contributions
    return _get_contributions()
