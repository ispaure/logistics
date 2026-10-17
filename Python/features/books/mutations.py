"""Portable metadata planning and content-preserving format rewrites."""
from commonUtils.archives.rebuilding import rewrite_members


def metadata_plan(document, changes):
    from .metadata import package_metadata
    return document.package_path, package_metadata(document, changes)


def rewrite_metadata(original, output, member, data, *, cancelled=lambda: False):
    return rewrite_members(original, output, {member: data},
        first=('mimetype',), stored=('mimetype',),
        max_member_bytes=128 * 1024 * 1024, cancelled=cancelled)


def validate_metadata(path):
    from .epub import EPUBBook
    return EPUBBook(path)
