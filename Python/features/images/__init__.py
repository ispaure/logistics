"""
Images feature integration for Logistics.
"""

FEATURE_DESCRIPTION = 'Compress images to WebP and edit JPG EXIF comments.'

FEATURE_NAME = "images"
FEATURE_LABEL = "Image Tools"


def get_contributions():
    from features.images.ui_contributions import get_contributions as _get_contributions
    return _get_contributions()


def register():
    return get_contributions()
