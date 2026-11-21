"""
Images feature integration for Logistics.
"""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

FEATURE_DESCRIPTION = 'Compress images to WebP and edit JPG EXIF comments.'

FEATURE_NAME = "images"
FEATURE_LABEL = "Image Tools"


def get_contributions():
    from features.images.ui_contributions import get_contributions as _get_contributions
    return _get_contributions()


def register():
    return get_contributions()
