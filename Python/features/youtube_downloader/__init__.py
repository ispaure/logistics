"""
YouTube Downloader feature integration for Logistics.
"""

FEATURE_NAME = 'youtube_downloader'
FEATURE_LABEL = 'YouTube Downloader'
FEATURE_OPTIONAL_DEPENDENCIES = ('rclone',)


def get_contributions():
    """Return UI contributions provided by this feature."""

    from features.youtube_downloader.ui_contributions import get_contributions as _get_contributions
    return _get_contributions()


def register():
    """Unified declaration; get_contributions remains a compatibility entry point."""
    return get_contributions()
