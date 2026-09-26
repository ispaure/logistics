"""
Dropbox feature integration for Logistics.
"""

FEATURE_NAME = "dropbox"
FEATURE_LABEL = "Dropbox"


def get_contributions():
    from features.dropbox.ui_contributions import get_contributions as _get_contributions
    return _get_contributions()
