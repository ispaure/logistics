"""
Obsidian feature integration for Logistics.
"""


FEATURE_NAME = "obsidian"
FEATURE_LABEL = "Obsidian"


def get_contributions():
    """Return UI contributions provided by this feature."""

    from features.obsidian.ui_contributions import get_contributions as _get_contributions
    return _get_contributions()
