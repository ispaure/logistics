"""
Links feature integration for Logistics.
"""

FEATURE_DESCRIPTION = 'Open your configured websites and service shortcuts from one page.'


FEATURE_NAME = "links"
FEATURE_LABEL = "Personal Links"


def get_contributions():
    """Return UI contributions provided by this feature."""

    from features.links.ui_contributions import get_contributions as _get_contributions
    return _get_contributions()


def register():
    """Unified declaration; get_contributions remains a compatibility entry point."""
    return get_contributions()
