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


def register_file_types():
    """Make the project's CBZ type available to all later shared file listings."""
    from commonUtils.fileTypes.registry import register_file_type
    from .cbz import CBZFile
    register_file_type(CBZFile, 'cbz')
