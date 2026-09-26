"""
Images feature integration for Logistics.
"""

FEATURE_NAME = "images"
FEATURE_LABEL = "Images"


def get_contributions():
    from features.images.ui_contributions import get_contributions as _get_contributions
    return _get_contributions()
