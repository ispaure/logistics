"""
Flight Simulator feature integration for Logistics.
"""

FEATURE_DESCRIPTION = 'Apply display and graphics presets to X-Plane 12.'


FEATURE_NAME = "flight_sim"
FEATURE_LABEL = "X-Plane Presets"


def get_contributions():
    """Return UI contributions provided by this feature."""

    from features.flight_sim.ui_contributions import get_contributions as _get_contributions
    return _get_contributions()


def register():
    """Unified declaration; get_contributions remains a compatibility entry point."""
    return get_contributions()
