"""Read and transactionally edit ComicInfo without extracting or converting pages."""

import os
from pathlib import Path
from hashlib import sha256
import stat
from tempfile import TemporaryDirectory
import zipfile

from .archive_io import archive_unchanged, validate_archive_members
from .comicinfo import ComicInfoXML
from commonUtils.archives.zip_access import open_archive, authenticate, copy_member_info, archive_manifest
from services.zip_passwords import resolve_password, remember_verified_password


class ComicDocument:
    def __init__(self, path, *, password=None):
        self.path = Path(path)
        self.snapshot = self.path.stat()
        validate_archive_members(self.path)
        self.password = resolve_password(self.path, password=password)
        with open_archive(self.path, password=self.password) as archive:
            matches = [info for info in archive.infolist()
                       if Path(info.filename).name.casefold() == 'comicinfo.xml']
            if len(matches) > 1:
                raise ValueError('Multiple ComicInfo.xml entries; cannot choose one safely')
            self.member = matches[0].filename if matches else 'ComicInfo.xml'
            if matches and matches[0].file_size > 4 * 1024 * 1024:
                raise ValueError('ComicInfo.xml is too large to edit')
            self.exists = bool(matches)
            data = archive.read(matches[0]) if matches else b'<ComicInfo />'
        if not archive_unchanged(self.path, self.snapshot):
            raise RuntimeError('Comic changed while loading; select it again')
        self.info = ComicInfoXML.from_bytes(data)

    def prepare_metadata(self, changes):
        """Validate edits on a copy; failures never alter the loaded document."""
        info = ComicInfoXML.from_bytes(self.info.to_bytes())
        for field, value in changes.items():
            info.set_field(field, value)
        info.to_bytes()  # Validate XML characters before callers stage a save.
        return info

    def save(self, changes):
        if self.path.is_symlink():
            raise ValueError('Cannot replace a symbolic link')
        if not archive_unchanged(self.path, self.snapshot):
            raise RuntimeError('Comic changed since loading; reload before saving')
        info = self.prepare_metadata(changes)
        data = info.to_bytes()
        if data == self.info.to_bytes():
            return
        if self.password is not None:
            authenticate(self.path, self.password, all_members=True, for_rewrite=True)
        with TemporaryDirectory(prefix='.logistics-comic-', dir=self.path.parent) as temp:
            staged = Path(temp) / 'edited.cbz'
            expected = {}
            with open_archive(self.path, password=self.password) as source, open_archive(
                    staged, 'w', password=self.password) as target:
                target.comment = source.comment
                for member in source.infolist():
                    output_info = copy_member_info(member, target)
                    if member.filename == self.member:
                        target.writestr(output_info, data)
                        expected[member.filename] = (len(data), sha256(data).hexdigest())
                    elif member.is_dir():
                        target.writestr(output_info, b'')
                        expected[member.filename] = None
                    else:
                        digest, length = sha256(), 0
                        with source.open(member) as incoming, target.open(output_info, 'w') as outgoing:
                            while chunk := incoming.read(1024 * 1024):
                                outgoing.write(chunk)
                                digest.update(chunk)
                                length += len(chunk)
                        expected[member.filename] = (length, digest.hexdigest())
                if not self.exists:
                    target.writestr(self.member, data, compress_type=zipfile.ZIP_DEFLATED)
                    expected[self.member] = (len(data), sha256(data).hexdigest())
            if archive_manifest(staged, password=self.password) != expected:
                raise ValueError('Archive content verification failed; original was kept')
            with staged.open('r+b') as stream:
                os.fsync(stream.fileno())
            staged.chmod(stat.S_IMODE(self.snapshot.st_mode))
            if not archive_unchanged(self.path, self.snapshot):
                raise RuntimeError('Comic changed while saving; original was kept')
            os.replace(staged, self.path)
        self.snapshot = self.path.stat()
        self.info = info
        self.exists = True
        remember_verified_password(self.path, self.password)
