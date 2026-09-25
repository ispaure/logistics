"""
Flight Simulator feature integration for Logistics.
"""


FEATURE_NAME = "flight_sim"
FEATURE_LABEL = "Flight Simulator"


def get_contributions():
    """Return UI contributions provided by this feature."""

    from features.flight_sim.ui_contributions import get_contributions as _get_contributions
    return _get_contributions()
