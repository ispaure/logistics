"""
Comics feature integration for Logistics.
"""


FEATURE_NAME = "comics"
FEATURE_LABEL = "Comics"
FEATURE_DEPENDENCIES = ("images",)


def get_contributions():
    """Return UI contributions provided by this feature."""

    from features.comics.ui_contributions import get_contributions as _get_contributions
    return _get_contributions()
