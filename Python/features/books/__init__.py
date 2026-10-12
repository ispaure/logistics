"""Standalone EPUB reading and editing, independent of Calibre."""

FEATURE_DESCRIPTION = 'Read EPUB books and comics, edit metadata and manage comic libraries.'


def register():
    from .contributions import register as declaration
    return declaration()
