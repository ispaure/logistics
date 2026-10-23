"""Transactional EPUB metadata updates, preserving unrelated ZIP resources."""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import os
import shutil
import stat
from tempfile import NamedTemporaryFile
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from threading import RLock

from .epub import OPF, DC, BookError, EPUBBook, parse_xml

EDITABLE = ('title', 'creator', 'language', 'publisher', 'subject', 'description')
_save_lock = RLock()


def package_metadata(book, changes):
    """Change only supplied Dublin Core fields; retain unknown fields/refinements."""
    if set(changes) - set(EDITABLE):
        raise BookError('Unsupported metadata field.')
    package = parse_xml(book.package_bytes)
    metadata = package.find(f'{{{OPF}}}metadata')
    for name, values in changes.items():
        if not isinstance(values, (list, tuple)) or any(not isinstance(value, str) for value in values):
            raise BookError('Metadata values must be lists of text.')
        values = [value.strip() for value in values if value.strip()]
        if name in ('title', 'language') and not values:
            raise BookError('Title and language cannot be empty.')
        existing = metadata.findall(f'{{{DC}}}{name}')
        # Preserve IDs and EPUB 2 attributes (role, file-as) on retained nodes.
        for index, value in enumerate(values):
            node = existing[index] if index < len(existing) else ET.SubElement(metadata, f'{{{DC}}}{name}')
            if (node.text or '').strip() != value:
                # Sort names belong to the previous value, not the edited value.
                node.attrib.pop(f'{{{OPF}}}file-as', None)
                for refinement in list(metadata):
                    if node.get('id') and refinement.get('refines') == '#' + node.get('id') and refinement.get('property') == 'file-as':
                        metadata.remove(refinement)
            node.text = value
        for node in existing[len(values):]:
            if node.get('id'):
                for refinement in list(metadata):
                    if refinement.get('refines') == '#' + node.get('id'):
                        metadata.remove(refinement)
            metadata.remove(node)
    if package.get('version', '').startswith('3'):
        modified = next((node for node in metadata if node.tag == f'{{{OPF}}}meta' and node.get('property') == 'dcterms:modified'), None)
        if modified is None:
            modified = ET.SubElement(metadata, f'{{{OPF}}}meta', {'property': 'dcterms:modified'})
        modified.text = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    # Keep prefixes used in QName-valued metadata (e.g. rendition:layout).
    from io import BytesIO
    namespaces = {}
    for _, (prefix, uri) in ET.iterparse(BytesIO(book.package_bytes), events=('start-ns',)):
        namespaces[prefix] = uri
        if not prefix.startswith('ns') or not prefix[2:].isdigit():
            ET.register_namespace(prefix, uri)
    result = ET.tostring(package, encoding='unicode')
    for prefix, uri in namespaces.items():
        marker = f'xmlns:{prefix}=' if prefix else 'xmlns='
        if marker not in result:
            from xml.sax.saxutils import quoteattr
            end = result.index('>')
            result = result[:end] + f' {marker}{quoteattr(uri)}' + result[end:]
    return ('<?xml version="1.0" encoding="utf-8"?>\n' + result).encode('utf-8')


def save_metadata(book, changes, *, cancelled=lambda: False):
    """Stage beside the book, validate, back up, then atomically replace it.

    Cancellation and external changes leave the original untouched. Backup names
    never overwrite an existing backup. Return (reloaded_book, backup_path).
    """
    # Serialize book writes in this process. Waiting callers check their original
    # fingerprint after acquisition, so a second reader cannot overwrite edits.
    from commonUtils.runtime.operations import OperationCancelled
    try:
        with _save_lock:
            if book.source is not None:
                return _save_private_metadata(book, changes, cancelled)
            return _save_metadata(book, changes, cancelled)
    except OperationCancelled:
        raise BookError('Metadata save cancelled; the original EPUB was kept.') from None


def _save_metadata(book, changes, cancelled):
    from commonUtils.persistence.publication import save_transaction
    from commonUtils.filesystem.snapshots import verified_file_snapshot
    from commonUtils.filesystem.local_access import check_local_path
    def check():
        check_local_path(book.path)
        if cancelled():
            raise BookError('Metadata save cancelled; the original EPUB was kept.')
        if book._signature() != book.signature:
            raise BookError('This book changed on disk. Reopen it before saving metadata.')
    check()
    updated = package_metadata(book, changes)
    staged = None
    backup = None
    expected = {}
    def stage():
        nonlocal staged
        with NamedTemporaryFile(dir=book.path.parent, prefix=f'.{book.path.name}.', suffix='.epub', delete=False) as temporary:
            staged = Path(temporary.name)
        with ZipFile(book.path) as original, ZipFile(staged, 'w') as output:
            from .mutations import rewrite_metadata
            expected.update(rewrite_metadata(original, output, book.package_path, updated, cancelled=cancelled))
    def verify():
        from commonUtils.archives.zip_access import archive_manifest
        if archive_manifest(staged) != expected:
            raise BookError('EPUB resource verification failed; original preserved.')
        EPUBBook(staged)
        shutil.copymode(book.path, staged)
        with staged.open('r+b') as stream:
            os.fsync(stream.fileno())
    def publish():
        nonlocal backup
        backup = book.path.with_name(book.path.name + '.bak')
        suffix = 1
        while True:
            try:
                destination = backup.open('xb')
                break
            except FileExistsError:
                backup = book.path.with_name(book.path.name + f'.bak.{suffix}')
                suffix += 1
        identity = None
        def owns_backup():
            try:
                current = backup.lstat()
            except OSError:
                return False  # Do not remove or alter a path whose ownership is unknown.
            return stat.S_ISREG(current.st_mode) and (current.st_dev, current.st_ino) == identity
        try:
            copied = sha256()
            with destination:
                opened = os.fstat(destination.fileno())
                identity = opened.st_dev, opened.st_ino
                with book.path.open('rb') as source:
                    while chunk := source.read(1024 * 1024):
                        check()
                        destination.write(chunk)
                        copied.update(chunk)
                destination.flush()
                os.fsync(destination.fileno())
            if not owns_backup():
                raise BookError(f'EPUB backup path changed; original preserved. Path retained: {backup}')
            shutil.copymode(book.path, backup)
            try:
                _, backup_digest = verified_file_snapshot(backup, cancelled=cancelled)
            except ValueError as error:
                raise BookError('EPUB backup changed during verification; original preserved.') from error
            if backup_digest != copied.digest():
                raise BookError('EPUB backup verification failed; original preserved.')
            check()
            if not owns_backup():
                raise BookError(f'EPUB backup path changed; original preserved. Path retained: {backup}')
        except BaseException:
            if owns_backup():
                backup.unlink(missing_ok=True)
            raise
        os.replace(staged, book.path)
    def cleanup():
        if staged is not None:
            staged.unlink(missing_ok=True)
    save_transaction(stage=stage, verify=verify, validate=check, publish=publish,
                     cleanup=cleanup, cancelled=cancelled)
    return EPUBBook(book.path), backup


def _save_private_metadata(book, changes, cancelled):
    from commonUtils.archives.zip_access import open_archive, archive_manifest
    from commonUtils.runtime.operations import check_cancelled
    from .mutations import metadata_plan, rewrite_metadata
    member, data = metadata_plan(book, changes)
    expected = {}
    def write(stream):
        check_cancelled(cancelled)
        with book.open_archive() as original, open_archive(stream, 'w', password=book.password) as output:
            expected.update(rewrite_metadata(original, output, member, data, cancelled=cancelled))
    def verify(path):
        check_cancelled(cancelled)
        with book.source.open(path) as stream:
            if archive_manifest(stream, password=book.password) != expected:
                raise BookError('EPUB resource verification failed; original preserved.')
        EPUBBook(path, source=book.source, password=book.password)
    # The provider owns cancellation during encryption and before publication.
    with book.source.operation(cancelled):
        book.source.replace_stream(book.path, write, expected_revision=book.signature, verify=verify)
    return EPUBBook(book.path, source=book.source, password=book.password), None
