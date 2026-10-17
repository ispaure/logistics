"""Recoverable publication of an imported archive and its checksum record.

Format patching belongs to features; this host transaction owns the UUID copy
and checksum record. The original external import is never rewritten.
"""
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZipFile
from commonUtils.persistence import atomic_write_json
from commonUtils.runtime.streams import file_sha256
from commonUtils.persistence.publication import mutation_lock
from commonUtils.runtime.operations import check_cancelled


class LibraryEdits:
    def edit_journal(self, key):
        self.path(key, '.json')  # Validate identity before constructing any paths.
        folder = self.root / '.edits'
        if folder.is_symlink():
            raise ValueError('Library edit storage cannot be a symbolic link.')
        folder.mkdir(exist_ok=True, mode=0o700)
        journal = folder / (key + '.json')
        if journal.is_symlink():
            raise ValueError('Library edit journal cannot be a symbolic link.')
        return journal

    def recover_edit(self, key):
        journal = self.edit_journal(key)
        if not journal.exists():
            return
        with mutation_lock:
            with journal.open('rb') as stream:
                data = stream.read(256 * 1024 + 1)
            if len(data) > 256 * 1024:
                raise ValueError('Library edit journal is oversized; it was preserved.')
            pending = json.loads(data)
            if not isinstance(pending, dict) or set(pending) != {'before', 'after'}:
                raise ValueError('Invalid library edit journal; it was preserved.')
            before = self.decode_record(key, json.dumps(pending['before']).encode())
            after = self.decode_record(key, json.dumps(pending['after']).encode())
            if before['kind'] != after['kind'] or after['revision'] != before['revision'] + 1:
                raise ValueError('Invalid library edit revision; journal was preserved.')
            record, _ = self._read_record(key)
            if record not in (before, after):
                raise ValueError('Library record changed during metadata publication; journal was preserved.')
            path = self.path(key, '.epub' if before['kind'] == 'epub' else '.cbz')
            digest = file_sha256(path)
            if digest == after['digest']:
                atomic_write_json(self.path(key, '.json'), after, max_bytes=128 * 1024, durable_directory=True)
            elif digest != before['digest'] or record != before:
                raise ValueError('Library archive changed during metadata publication; journal was preserved.')
            journal.unlink()

    def save_metadata(self, record, reader, changes, *, cancelled=lambda: False):
        from features.books import mutations as book_edits
        from features.comics import mutations as comic_edits
        from commonUtils.archives.zip_access import archive_manifest
        key, temporary = record['id'], None
        with mutation_lock:
            current, opened = self.open(key)
            if current != record:
                raise OSError('Library record changed; reopen it before editing metadata.')
            if not changes:
                return current, opened
            epub = record['kind'] == 'epub'
            format_edits = book_edits if epub else comic_edits
            path = self.path(key, '.epub' if epub else '.cbz')
            with ZipFile(path) as archive:
                if any(info.flag_bits & 1 for info in archive.infolist()):
                    raise ValueError('Editing standalone encrypted imports requires a native archive writer.')
            member, data = format_edits.metadata_plan(opened if epub else opened.document, changes)
            if not epub and data == opened.document.info.to_bytes():
                return current, opened
            try:
                check_cancelled(cancelled)
                with NamedTemporaryFile(dir=self.root, prefix='.metadata-', delete=False) as stream:
                    temporary = Path(stream.name)
                with ZipFile(path) as original, ZipFile(temporary, 'w') as output:
                    expected = format_edits.rewrite_metadata(original, output, member, data, cancelled=cancelled)
                if archive_manifest(temporary) != expected:
                    raise ValueError('Metadata verification failed; original preserved.')
                format_edits.validate_metadata(temporary)
                with temporary.open('r+b') as stream:
                    os.fsync(stream.fileno())
                updated = dict(record, digest=file_sha256(temporary), revision=record['revision'] + 1)
                self.decode_record(key, json.dumps(updated).encode())
                if self.read_record(key)[0] != record or file_sha256(path) != record['digest']:
                    raise OSError('Library changed during metadata editing; original preserved.')
                check_cancelled(cancelled)
                journal = self.edit_journal(key)
                atomic_write_json(journal, dict(before=record, after=updated), max_bytes=256 * 1024,
                                  durable_directory=True)
                # No cancellation after publication starts: finish both records,
                # or leave the journal for deterministic recovery on next open.
                os.replace(temporary, path)
                temporary = None
                atomic_write_json(self.path(key, '.json'), updated, max_bytes=128 * 1024, durable_directory=True)
                journal.unlink()
                self.verified.clear()
                return self.open(key)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)

    def edit_comics(self, records, changes, *, cancelled=lambda: False):
        """Preflight all selections, then publish independently per comic."""
        prepared = []
        for record in records:
            check_cancelled(cancelled)
            if record['kind'] != 'comic':
                raise ValueError('Batch comic metadata requires comic selections.')
            current, reader = self.open(record['id'])
            if current != record:
                raise OSError('A selected comic changed; reopen the batch editor.')
            reader.document.prepare_metadata(changes)
            prepared.append((record, reader))
        completed, failures = [], []
        for record, reader in prepared:
            if cancelled():
                break
            try:
                updated, _ = self.save_metadata(record, reader, changes)
                completed.append(updated)
            except Exception as error:
                failures.append((record['id'], str(error)))
        return completed, failures
