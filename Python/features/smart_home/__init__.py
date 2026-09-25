"""
Smart Home feature integration for Logistics.
"""


FEATURE_NAME = 'smart_home'
FEATURE_LABEL = 'Smart Home'


def get_contributions():
    """Return UI contributions provided by this feature."""

    from features.smart_home.ui_contributions import get_contributions as _get_contributions
    return _get_contributions()
