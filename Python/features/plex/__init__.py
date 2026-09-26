"""
Plex feature integration for Logistics.
"""

FEATURE_NAME = "plex"
FEATURE_LABEL = "Plex"


def get_contributions():
    from features.plex.ui_contributions import get_contributions as _get_contributions
    return _get_contributions()
