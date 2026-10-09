"""Standalone EPUB reading and editing, independent of Calibre."""


def register():
    from .contributions import register as declaration
    return declaration()
