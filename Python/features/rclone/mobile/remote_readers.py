"""Memory-only remote documents, with complete in-memory remote archive snapshots."""
import base64
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path
from threading import Event, Thread
from uuid import uuid4

from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.range_reader import RangeReader
from services.documents.archive_access import NativeArchiveAccess
from services.documents.readers import PrivateReader
from features.rclone.remote_policy import direct_kind, TEXT_LIMIT, LocalCopyRequired


class RemoteSource(NativeArchiveAccess):
    archive_action = 'remote_archive'
    private = True
    archive_limit = 128 * 1024 * 1024

    def __init__(self, client, remote, path, *, password='', cancelled=lambda: False, progress=lambda message: None):
        self.client, self.remote, self.path = client, remote, path
        self.generation = client.generation
        self.identity = client.connection_identity(remote)
        self.password, self.cancelled = password, cancelled
        self.progress = progress
        self.headers, self.cache, self.cache_bytes = None, OrderedDict(), 0
        self.cache_token = None
        self.closed = False
        info = self.request('remote_stat')
        self.size, self.expected = info['size'], info['revision']

    def check(self):
        check_cancelled(self.cancelled)
        if self.closed or self.client.generation != self.generation:
            self.close()
            raise ValueError('Credentials changed or were locked. Reopen the remote.')

    def version(self, path):
        self.check()
        if self.cache_token is not None:
            return self.expected
        result = self.request('remote_stat')
        if result['revision'] != self.expected:
            raise ValueError('The remote file changed. Reopen it.')
        return self.expected

    def request(self, action, **values):
        self.check()
        if action == self.archive_action and not values and self.headers is not None:
            return self.headers
        if action == self.archive_action and self.cache_token is not None:
            action = 'remote_cache_archive'
            values['run'] = self.cache_token
        elif action == 'remote_stat':
            self.progress('Checking remote file and connection')
        elif action == self.archive_action:
            member = values.get('member')
            self.progress('Reading remote archive member: ' + member if member else 'Reading remote archive index')
        else:
            self.progress('Reading remote file data')
        result = self.client.request(action, remote=self.remote, path=self.path, identity=self.identity,
            expected=getattr(self, 'expected', ''), password=self.password, **values)
        self.check()
        if action in {self.archive_action, 'remote_cache_archive'} and not values.get('member'):
            self.headers = result
        return result

    def cache_archive(self):
        """One native network stream into RAM; progress/control bypass network locks."""
        if self.size > self.archive_limit:
            raise LocalCopyRequired()
        token, stopped = uuid4().hex, Event()
        self.cache_token = token
        def poll():
            previous = None
            while not stopped.wait(.25):
                try:
                    status = self.client.request('remote_cache_status', run=token)
                    total, done = status['total'], status['done']
                    if total and (done, total) != previous:
                        previous = done, total
                        self.progress(f'Downloading archive to memory: {100 * done // total}% '
                                      f'({done / 1048576:.1f} / {total / 1048576:.1f} MiB)')
                except Exception:
                    return
        worker = Thread(target=poll, daemon=True)
        self.progress('Downloading archive to memory: 0%')
        worker.start()
        try:
            self.client.request('remote_cache_open', remote=self.remote, path=self.path,
                                identity=self.identity, expected=self.expected, run=token)
            self.check()
        except Exception:
            self.close()
            raise
        finally:
            stopped.set()
            worker.join()
        self.progress('Archive downloaded: 100% · Preparing reader from memory')

    @contextmanager
    def open(self, path):
        def read(offset, count):
            return base64.b64decode(self.request('remote_range', offset=offset, count=count)['data'], validate=True)
        with RangeReader(self.size, read, cache_blocks=2, max_read=16*1024*1024, validate=self.check) as stream:
            yield stream

    def close(self):
        self.closed = True
        token, self.cache_token = self.cache_token, None
        if token is not None:
            self.client.request('remote_cache_close', run=token)
        super().close()


class RemoteReaders:
    # Credential-bound sessions use the existing private session revocation path.
    encrypted = True
    remote_storage = True

    def __init__(self, client, remote, *, progress=lambda message: None):
        self.client, self.remote = client, remote
        self.progress = progress
        self.root = Path('/remote') / str(client.generation) / remote

    def open(self, key, *, password='', cancelled=lambda: False):
        self.progress('Checking remote connection')
        source = RemoteSource(self.client, self.remote, key, password=password, cancelled=cancelled,
                              progress=self.progress)
        try:
            kind = direct_kind(key, source.size)
            if kind == 'text':
                with source.open(key) as stream:
                    reader = PrivateReader(key, stream.read(TEXT_LIMIT + 1))
                reader.source = source
            elif kind == 'image':
                with source.open(key) as stream:
                    data = stream.read()
                reader = RemoteImageReader(key, data, source)
            else:
                if Path(key).suffix.lower() in {'.epub', '.cbz', '.zip'}:
                    source.cache_archive()
                reader = PrivateReader(key, source=source)
            reader.key, reader.password, reader.read_only = key, password, True
            return reader
        except Exception:
            source.close()
            raise


class RemoteImageReader:
    editable = False
    book = None
    read_only = True
    image_document = True

    def __init__(self, name, data, source):
        self.name, self.data, self.source = name, data, source
        self.kind = Path(name).suffix.lower()
        self.labels = [Path(name).name]

    def page(self, index):
        self.source.check()
        return 'image', self.data
