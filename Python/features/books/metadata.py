"""Transactional EPUB metadata updates, preserving unrelated ZIP resources."""
from datetime import datetime, timezone
from pathlib import Path
import os
import shutil
from tempfile import NamedTemporaryFile
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_STORED
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
    with _save_lock:
        return _save_metadata(book, changes, cancelled)


def _save_metadata(book, changes, cancelled):
    def check():
        if cancelled():
            raise BookError('Metadata save cancelled; the original EPUB was kept.')
        if book._signature() != book.signature:
            raise BookError('This book changed on disk. Reopen it before saving metadata.')
    check()
    updated = package_metadata(book, changes)
    with NamedTemporaryFile(dir=book.path.parent, prefix=f'.{book.path.name}.', suffix='.epub', delete=False) as temporary:
        staged = Path(temporary.name)
    try:
        with ZipFile(book.path) as original, ZipFile(staged, 'w') as output:
            output.comment = original.comment
            infos = sorted(original.infolist(), key=lambda info: info.filename != 'mimetype')
            for info in infos:
                check()
                if info.filename == 'mimetype':
                    output.writestr(info, b'application/epub+zip', compress_type=ZIP_STORED)
                elif info.filename == book.package_path:
                    output.writestr(info, updated)
                else:
                    with original.open(info) as source, output.open(info, 'w') as destination:
                        while chunk := source.read(1024 * 1024):
                            check()
                            destination.write(chunk)
        EPUBBook(staged)  # Do not replace the original with an unreadable package.
        shutil.copymode(book.path, staged)
        with staged.open('r+b') as stream:
            os.fsync(stream.fileno())
        check()
        backup = book.path.with_name(book.path.name + '.bak')
        suffix = 1
        while True:
            try:
                destination = backup.open('xb')
                break
            except FileExistsError:
                backup = book.path.with_name(book.path.name + f'.bak.{suffix}')
                suffix += 1
        try:
            with destination, book.path.open('rb') as source:
                while chunk := source.read(1024 * 1024):
                    check()
                    destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())
            shutil.copymode(book.path, backup)
            check()
        except BaseException:
            backup.unlink(missing_ok=True)
            raise
        os.replace(staged, book.path)
        return EPUBBook(book.path), backup
    finally:
        staged.unlink(missing_ok=True)
