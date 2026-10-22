"""Lazy native archive views shared by ordinary and encrypted document sources."""
import base64
from contextlib import contextmanager
from zipfile import ZipInfo
from commonUtils.archives.callbacks import CallbackArchive


class NativeArchive(CallbackArchive):
    def __init__(self, source):
        self.source = source
        self.members = []
        for row in source.request(source.archive_action):
            info = ZipInfo(row['name'])
            info.file_size, info.CRC = row['size'], row['crc']
            info.flag_bits = 0  # This facade exposes authenticated decoded members.
            self.members.append(info)
        self.protected = [row['name'] for row in source.headers if row['flags'] & 1 and not row['directory']]
        super().__init__(self.members, read_member=source.read_member, manifest=self._native_manifest)

    def _native_manifest(self):
        action = getattr(self.source, 'manifest_action', None)
        if action is None:
            raise ValueError('This archive source does not provide a content manifest.')
        return self.source.request(action)


class NativeArchiveAccess:
    """One lazy decoded-member facade for ordinary and LocalCrypt archive adapters."""
    archive_action = 'file_archive'
    max_read = 16 * 1024 * 1024
    cache_limit = 8 * 1024 * 1024

    def _check_archive_version(self, path):
        if self.version(path) != self.expected:
            raise ValueError('The archive changed; reopen it.')

    @contextmanager
    def open_archive(self, path, password=None):
        self._check_archive_version(path)
        if password is not None and password != self.password:
            self.cache.clear()
            self.cache_bytes = 0
            self.password = password
        archive = NativeArchive(self)
        if archive.protected:
            # Validate the supplied inner password before presenting a reader.
            candidates = [info for info in archive.members if info.filename in archive.protected]
            archive.read(min(candidates, key=lambda info: info.file_size))
        yield archive
        self._check_archive_version(path)

    def archive_password(self, path):
        return self.password or None

    def read_member(self, member):
        self._check_archive_version(self.path)
        key = member, self.password
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        data = base64.b64decode(self.request(self.archive_action, member=member)['data'], validate=True)
        if len(data) > self.max_read:
            raise ValueError('Archive member exceeds the read buffer limit.')
        self.cache[key] = data
        self.cache_bytes += len(data)
        while self.cache_bytes > self.cache_limit or len(self.cache) > 32:
            _, removed = self.cache.popitem(last=False)
            self.cache_bytes -= len(removed)
        return data

    def close(self):
        self.password = None
        self.headers = None
        self.cache.clear()
        self.cache_bytes = 0
