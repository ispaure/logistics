"""Portable metadata planning and content-preserving format rewrites."""
from commonUtils.archives.rebuilding import rewrite_members


def metadata_plan(document, changes):
    return document.member, document.prepare_metadata(changes).to_bytes()


def rewrite_metadata(original, output, member, data, *, cancelled=lambda: False):
    return rewrite_members(original, output, {member: data},
        max_member_bytes=128 * 1024 * 1024, cancelled=cancelled)


def validate_metadata(path):
    from .library import ComicDocument
    return ComicDocument(path)
