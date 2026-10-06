"""Read and transactionally edit ComicInfo without extracting or converting pages."""

import os
from pathlib import Path
import shutil
import stat
from tempfile import TemporaryDirectory
import zipfile

from .archive_io import archive_unchanged, validate_archive_members
from .comicinfo import ComicInfoXML


class ComicDocument:
    def __init__(self, path):
        self.path = Path(path)
        self.snapshot = self.path.stat()
        validate_archive_members(self.path)
        with zipfile.ZipFile(self.path) as archive:
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
        with TemporaryDirectory(prefix='.logistics-comic-', dir=self.path.parent) as temp:
            staged = Path(temp) / 'edited.cbz'
            with zipfile.ZipFile(self.path) as source, zipfile.ZipFile(staged, 'w') as target:
                target.comment = source.comment
                expected = {}
                for member in source.infolist():
                    if member.filename == self.member:
                        target.writestr(member, data)
                    else:
                        expected[member.filename] = (member.file_size, member.CRC)
                        with source.open(member) as incoming, target.open(member, 'w') as outgoing:
                            shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
                if not self.exists:
                    target.writestr(self.member, data, compress_type=zipfile.ZIP_DEFLATED)
            with zipfile.ZipFile(staged) as verified:
                if verified.testzip() is not None:
                    raise ValueError('Archive verification failed')
                if verified.read(self.member) != data:
                    raise ValueError('Metadata verification failed')
                for name, signature in expected.items():
                    member = verified.getinfo(name)
                    if (member.file_size, member.CRC) != signature:
                        raise ValueError(f'Archive member changed: {name}')
            staged.chmod(stat.S_IMODE(self.snapshot.st_mode))
            with staged.open('rb') as stream:
                os.fsync(stream.fileno())
            if not archive_unchanged(self.path, self.snapshot):
                raise RuntimeError('Comic changed while saving; original was kept')
            os.replace(staged, self.path)
        self.snapshot = self.path.stat()
        self.info = info
        self.exists = True
