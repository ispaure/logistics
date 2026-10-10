"""
Links feature integration for Logistics.
"""


FEATURE_NAME = "links"
FEATURE_LABEL = "Links"


def get_contributions():
    """Return UI contributions provided by this feature."""

    from features.links.ui_contributions import get_contributions as _get_contributions
    return _get_contributions()


def register():
    """Unified declaration; get_contributions remains a compatibility entry point."""
    return get_contributions()
