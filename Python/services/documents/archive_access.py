"""Lazy native archive views shared by ordinary and encrypted document sources."""
import base64
from collections import OrderedDict
from contextlib import contextmanager
from threading import RLock
from zipfile import ZipInfo
from commonUtils.archives.callbacks import CallbackArchive


class NativeArchive(CallbackArchive):
    def __init__(self, source):
        self.source = source
        self.members = []
        rows = source.request(source.archive_action)
        for row in rows:
            info = ZipInfo(row['name'])
            info.file_size, info.CRC = row['size'], row['crc']
            info.flag_bits = 0  # This facade exposes authenticated decoded members.
            self.members.append(info)
        self.protected = [row['name'] for row in rows if row['flags'] & 1 and not row['directory']]
        super().__init__(self.members, read_member=source.read_member, manifest=self._native_manifest)

    def _native_manifest(self):
        action = getattr(self.source, 'manifest_action', None)
        if action is None:
            raise ValueError('This archive source does not provide a content manifest.')
        return self.source.request(action)


class NativeArchiveAccess:
    """Own one decoded archive lifetime; sources supply version and _request.

    Native work runs outside the cache lock so close never waits for I/O.
    Each request captures its password and revision before dispatch; changing
    the password back cannot revive an older result. Publication cannot refill
    a closed session or count concurrently read members twice.
    """
    archive_action = 'file_archive'
    max_read = 16 * 1024 * 1024
    cache_limit = 8 * 1024 * 1024

    def __init__(self, *, password=''):
        self._archive_lock = RLock()
        self.closed = False
        self.password = password
        self._password_revision = 0
        self.headers = None
        self.cache, self.cache_bytes = OrderedDict(), 0

    def _check_open(self):
        if self.closed:
            raise ValueError('This archive source is closed. Reopen it.')

    def check(self):
        self._check_archive_version(self.path)

    def _check_archive_version(self, path):
        self._check_open()
        if self.version(path) != self.expected:
            raise ValueError('The archive changed; reopen it.')
        self._check_open()

    def request(self, action, **values):
        self.check()
        headers = action == self.archive_action and not values
        with self._archive_lock:
            self._check_open()
            password, revision = self.password, self._password_revision
            if headers and self.headers is not None:
                return self.headers
        result = self._request(action, password=password, **values)
        self.check()
        with self._archive_lock:
            self._check_open()
            if revision != self._password_revision:
                raise ValueError('The archive password changed while reading. Reopen it.')
            if headers:
                self.headers = result
            return result

    def _request(self, action, *, password, **values):
        raise NotImplementedError

    @contextmanager
    def open_archive(self, path, password=None):
        self._check_archive_version(path)
        with self._archive_lock:
            self._check_open()
            if password is not None and password != self.password:
                self.cache.clear()
                self.cache_bytes = 0
                self.password = password
                self._password_revision += 1
        archive = NativeArchive(self)
        if archive.protected:
            # Validate the supplied inner password before presenting a reader.
            candidates = [info for info in archive.members if info.filename in archive.protected]
            archive.read(min(candidates, key=lambda info: info.file_size))
        self._check_archive_version(path)
        yield archive
        self._check_archive_version(path)

    def archive_password(self, path):
        self._check_archive_version(path)
        return self.password or None

    def read_member(self, member):
        self._check_archive_version(self.path)
        with self._archive_lock:
            self._check_open()
            key = member, self._password_revision
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
        data = base64.b64decode(self.request(self.archive_action, member=member)['data'], validate=True)
        if len(data) > self.max_read:
            raise ValueError('Archive member exceeds the read buffer limit.')
        self._check_archive_version(self.path)
        with self._archive_lock:
            self._check_open()
            if key != (member, self._password_revision):
                raise ValueError('The archive password changed while reading. Reopen it.')
            if key not in self.cache:
                self.cache[key] = data
                self.cache_bytes += len(data)
            while self.cache_bytes > self.cache_limit or len(self.cache) > 32:
                _, removed = self.cache.popitem(last=False)
                self.cache_bytes -= len(removed)
            return data

    def close(self):
        with self._archive_lock:
            self.closed = True
            self.password = None
            self.headers = None
            self.cache.clear()
            self.cache_bytes = 0
