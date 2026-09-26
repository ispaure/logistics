"""
Media feature integration for Logistics.
"""

FEATURE_NAME = "media"
FEATURE_LABEL = "Media"


def get_contributions():
    from features.media.ui_contributions import get_contributions as _get_contributions
    return _get_contributions()
