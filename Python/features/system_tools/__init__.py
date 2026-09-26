"""
System Tools feature integration for Logistics.
"""

FEATURE_NAME = "system_tools"
FEATURE_LABEL = "System Tools"


def get_contributions():
    from features.system_tools.ui_contributions import get_contributions as _get_contributions
    return _get_contributions()
