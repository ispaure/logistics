"""Shared comic/EPUB metadata plans and content-preserving archive rewrites.

Storage adapters own encryption and atomic publication. Plans contain only the
single metadata member to replace; unrelated resources must remain byte-identical.
"""
from hashlib import sha256
import zipfile

from commonUtils.archives.zip_access import copy_member_info
from commonUtils.runtime.operations import check_cancelled


def comic_metadata(document, changes):
    return document.member, document.prepare_metadata(changes).to_bytes()


def epub_metadata(book, changes):
    from features.books.metadata import package_metadata
    return book.package_path, package_metadata(book, changes)


def content_manifest(archive, *, cancelled=lambda: False):
    native_manifest = getattr(archive, 'content_manifest', None)
    if native_manifest is not None:
        return native_manifest(cancelled=cancelled)
    result = {}
    for member in archive.infolist():
        check_cancelled(cancelled)
        if member.is_dir():
            result[member.filename] = None
            continue
        digest, length = sha256(), 0
        with archive.open(member) as source:
            while chunk := source.read(1024 * 1024):
                check_cancelled(cancelled)
                digest.update(chunk)
                length += len(chunk)
        result[member.filename] = (length, digest.hexdigest())
    return result


def patched_manifest(archive, member, data, *, cancelled=lambda: False):
    result = content_manifest(archive, cancelled=cancelled)
    result[member] = len(data), sha256(data).hexdigest()
    return result


def rewrite_metadata(original, output, member, data, *, epub=False, cancelled=lambda: False):
    """Copy resources without conversion, updating only the planned XML member."""
    output.comment = original.comment
    expected = {}
    members = original.infolist()
    if epub:
        members = sorted(members, key=lambda info: info.filename != 'mimetype')
    for info in members:
        check_cancelled(cancelled)
        target = copy_member_info(info, output)
        if epub and info.filename == 'mimetype':
            target.compress_type = zipfile.ZIP_STORED
        if info.filename == member:
            output.writestr(target, data)
            expected[member] = len(data), sha256(data).hexdigest()
        elif info.is_dir():
            output.writestr(target, b'')
            expected[info.filename] = None
        else:
            if info.file_size > 128 * 1024 * 1024:
                raise ValueError('Archive member exceeds the metadata processing limit.')
            digest, length = sha256(), 0
            with original.open(info) as incoming, output.open(target, 'w') as outgoing:
                while chunk := incoming.read(1024 * 1024):
                    check_cancelled(cancelled)
                    outgoing.write(chunk)
                    digest.update(chunk)
                    length += len(chunk)
            expected[info.filename] = length, digest.hexdigest()
    if member not in expected:
        output.writestr(member, data, compress_type=zipfile.ZIP_DEFLATED)
        expected[member] = len(data), sha256(data).hexdigest()
    return expected
