"""
Plex feature integration for Logistics.
"""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

FEATURE_DESCRIPTION = 'Back up and restore Plex Media Server data with rclone.'

FEATURE_NAME = 'plex'
FEATURE_LABEL = 'Plex'
FEATURE_DEPENDENCIES = ('rclone',)


def get_contributions():
    """Return UI contributions provided by this feature."""

    from features.plex.ui_contributions import get_contributions as _get_contributions
    return _get_contributions()


def register():
    """Unified declaration; get_contributions remains a compatibility entry point."""
    return get_contributions()
