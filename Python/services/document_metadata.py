"""Shared comic/EPUB metadata plans and content-preserving archive rewrites.

Storage adapters own encryption and atomic publication. Plans contain only the
single metadata member to replace; unrelated resources must remain byte-identical.
"""
from commonUtils.archives.rebuilding import rewrite_members

def comic_metadata(document, changes):
    return document.member, document.prepare_metadata(changes).to_bytes()


def epub_metadata(book, changes):
    from features.books.metadata import package_metadata
    return book.package_path, package_metadata(book, changes)


def rewrite_metadata(original, output, member, data, *, epub=False, cancelled=lambda: False):
    """Apply the feature's metadata plan, preserving EPUB container requirements."""
    return rewrite_members(original, output, {member: data},
        first=('mimetype',) if epub else (), stored=('mimetype',) if epub else (),
        max_member_bytes=128 * 1024 * 1024, cancelled=cancelled)
