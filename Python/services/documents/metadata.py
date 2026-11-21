"""Compatibility dispatch to feature-owned metadata operations.

Storage adapters own encryption and atomic publication. New callers use the
owning feature's mutations module directly.
"""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"


def comic_metadata(document, changes):
    from features.comics.mutations import metadata_plan
    return metadata_plan(document, changes)


def epub_metadata(book, changes):
    from features.books.mutations import metadata_plan
    return metadata_plan(book, changes)


def rewrite_metadata(original, output, member, data, *, epub=False, cancelled=lambda: False):
    if epub:
        from features.books.mutations import rewrite_metadata as rewrite
    else:
        from features.comics.mutations import rewrite_metadata as rewrite
    return rewrite(original, output, member, data, cancelled=cancelled)
