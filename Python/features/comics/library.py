"""Read and transactionally edit ComicInfo without extracting or converting pages."""

import os
from contextlib import contextmanager
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import zipfile

from .archive_io import archive_unchanged, validate_archive_members
from .comicinfo import ComicInfoXML
from commonUtils.archives.zip_access import open_archive, authenticate, archive_manifest
from services.documents.storage import DocumentPolicy
from services.documents.zip_passwords import resolve_password, remember_verified_password


MAX_METADATA_BYTES = 4 * 1024 * 1024


class ComicDocument:
    def __init__(self, path, *, password=None, source=None):
        self.path = Path(path)
        self.source = source
        self.private = not DocumentPolicy.for_provider(source).persistent
        if source is None:
            self.snapshot = self.path.stat()
            validate_archive_members(self.path)
            self.password = resolve_password(self.path, password=password)
        elif hasattr(source, 'open_archive'):
            self.snapshot = source.version(self.path)
            self.password = password if password is not None else source.archive_password(self.path)
        else:
            from commonUtils.archives.zip_access import validate_members, ArchivePasswordError
            self.snapshot = source.version(self.path)
            with source.open(self.path) as stream, zipfile.ZipFile(stream) as archive:
                validate_members(archive)
                if len(archive.infolist()) > 10000:
                    raise ValueError('Comic contains too many entries.')
                protected = [entry for entry in archive.infolist() if entry.flag_bits & 1 and not entry.is_dir()]
                if protected and protected[0].file_size > 128 * 1024 * 1024:
                    raise ValueError('Encrypted comic page exceeds its memory limit.')
            self.password = password if password is not None else source.archive_password(self.path) if protected else None
            if protected and self.password is None:
                raise ArchivePasswordError('Archive password required: ' + self.path.name)
            if protected:
                with source.open(self.path) as stream:
                    authenticate(stream, self.password)
        with self.open_archive() as archive:
            matches = [info for info in archive.infolist()
                       if Path(info.filename).name.casefold() == 'comicinfo.xml']
            if len(matches) > 1:
                raise ValueError('Multiple ComicInfo.xml entries; cannot choose one safely')
            self.member = matches[0].filename if matches else 'ComicInfo.xml'
            if matches and matches[0].file_size > MAX_METADATA_BYTES:
                raise ValueError('ComicInfo.xml is too large to edit')
            self.exists = bool(matches)
            data = archive.read(matches[0]) if matches else b'<ComicInfo />'
        if not self.unchanged():
            raise RuntimeError('Comic changed while loading; select it again')
        self.info = ComicInfoXML.from_bytes(data)

    @contextmanager
    def open_archive(self):
        if self.source is None:
            with open_archive(self.path, password=self.password) as archive:
                yield archive
        elif hasattr(self.source, 'open_archive'):
            with self.source.open_archive(self.path, self.password) as archive:
                yield archive
        else:
            with self.source.open(self.path) as stream, open_archive(stream, password=self.password) as archive:
                yield archive

    def unchanged(self):
        if self.source is None:
            return archive_unchanged(self.path, self.snapshot)
        try:
            return self.source.version(self.path) == self.snapshot
        except (OSError, ValueError):
            return False

    def prepare_metadata(self, changes):
        """Validate edits on a copy; failures never alter the loaded document."""
        info = ComicInfoXML.from_bytes(self.info.to_bytes())
        for field, value in changes.items():
            info.set_field(field, value)
        data = info.to_bytes()  # Validate XML characters before callers stage a save.
        if len(data) > MAX_METADATA_BYTES:
            raise ValueError('Edited ComicInfo.xml exceeds the 4 MiB editing limit.')
        return info

    def save(self, changes):
        if self.source is not None:
            return self._save_source(changes)
        from services.documents.storage import document_transaction as save_transaction
        from commonUtils.filesystem.local_access import check_local_path
        def validate():
            check_local_path(self.path)
            if self.path.is_symlink():
                raise ValueError('Cannot replace a symbolic link')
            if not archive_unchanged(self.path, self.snapshot):
                raise RuntimeError('Comic changed since loading; reload before saving')
        validate()
        info = self.prepare_metadata(changes)
        data = info.to_bytes()
        if data == self.info.to_bytes():
            return
        if self.password is not None:
            authenticate(self.path, self.password, all_members=True, for_rewrite=True)
        with TemporaryDirectory(prefix='.logistics-comic-', dir=self.path.parent) as temp:
            staged = Path(temp) / 'edited.cbz'
            expected = {}
            def stage():
                with open_archive(self.path, password=self.password) as source, open_archive(
                        staged, 'w', password=self.password) as target:
                    from .mutations import rewrite_metadata
                    expected.update(rewrite_metadata(source, target, self.member, data))
            def verify():
                if archive_manifest(staged, password=self.password) != expected:
                    raise ValueError('Archive content verification failed; original was kept')
                with staged.open('r+b') as stream:
                    os.fsync(stream.fileno())
                staged.chmod(stat.S_IMODE(self.snapshot.st_mode))
            save_transaction(stage=stage, verify=verify, validate=validate,
                             publish=lambda: os.replace(staged, self.path),
                             cleanup=lambda: staged.unlink(missing_ok=True))
        self.snapshot = self.path.stat()
        self.info = info
        self.exists = True
        remember_verified_password(self.path, self.password)


    def _save_source(self, changes):
        """Stream a verified replacement through the host's document storage writer."""
        if not self.unchanged():
            raise ValueError('Comic changed since loading; reopen before saving.')
        info = self.prepare_metadata(changes)
        data = info.to_bytes()
        if data == self.info.to_bytes():
            return
        if self.password is not None:
            with self.source.open(self.path) as stream:
                authenticate(stream, self.password, all_members=True, for_rewrite=True)
        expected = {}
        def write(output):
            with self.open_archive() as incoming, open_archive(output, 'w', password=self.password) as outgoing:
                from .mutations import rewrite_metadata
                expected.update(rewrite_metadata(incoming, outgoing, self.member, data))
        def verify(path):
            with self.source.open(path) as stream:
                if archive_manifest(stream, password=self.password) != expected:
                    raise ValueError('Archive content verification failed; original kept.')
        from services.documents.storage import publish_document_stream
        publish_document_stream(self.source, self.path, write, expected_revision=self.snapshot, verify=verify)
        self.snapshot = self.source.version(self.path)
        self.info, self.exists = info, True
