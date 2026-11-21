"""Standalone EPUB reading and editing, independent of Calibre."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

FEATURE_DESCRIPTION = 'Read EPUB books and comics, edit metadata and manage comic libraries.'


def register():
    from .contributions import register as declaration
    return declaration()
