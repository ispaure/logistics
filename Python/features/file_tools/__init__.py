"""
File maintenance and diagnostic tools for Logistics.
"""

FEATURE_NAME = "file_tools"
FEATURE_LABEL = "File Tools"


def get_contributions():
    from features.file_tools.ui_contributions import get_contributions as _get_contributions
    return _get_contributions()


def register():
    return get_contributions()
