"""
Dropbox feature integration for Logistics.
"""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

FEATURE_DESCRIPTION = 'Browse local Dropbox folders and review conflicting copies.'

FEATURE_NAME = "dropbox"
FEATURE_LABEL = "Dropbox"


def get_contributions():
    from features.dropbox.ui_contributions import get_contributions as _get_contributions
    return _get_contributions()


def register():
    """Unified declaration; get_contributions remains a compatibility entry point."""
    return get_contributions()
