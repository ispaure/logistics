"""
Media feature integration for Logistics.
"""

FEATURE_DESCRIPTION = 'Rename MKA audio files using a CSV mapping.'

FEATURE_NAME = "media"
FEATURE_LABEL = "Media Tools"


def get_contributions():
    from features.media.ui_contributions import get_contributions as _get_contributions
    return _get_contributions()


def register():
    """Unified declaration; get_contributions remains a compatibility entry point."""
    return get_contributions()
