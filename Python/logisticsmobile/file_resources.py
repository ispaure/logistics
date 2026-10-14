"""Local mobile folder providers; crypt naming/bytes stay in the native bridge."""
from contextlib import contextmanager
from io import BytesIO
import base64
from pathlib import Path
from uuid import uuid4

from commonUtils.runtime.local_files import LocalFiles
from commonUtils.runtime.resource_provider import ResourceCapabilities
from commonUtils.persistence.publication import mutation_lock, rename_exclusive
from commonUtils.runtime.operations import check_cancelled
from .localcrypt import LocalCryptCopies


class CryptTransferStream(BytesIO):
    """Logical bytes plus a scoped native rewrap source, owned by Logistics.

    The provider keeps the encrypted file open for this stream's context. No
    descriptor is retained after closure and generic consumers only read bytes.
    """
    def __init__(self, data, record, encrypted):
        super().__init__(data)
        self._record = dict(record)
        self._encrypted = encrypted

    def transfer_source(self):
        if self.closed or self._encrypted.closed:
            raise ValueError('The encrypted transfer source is closed.')
        if self.tell() != 0:
            raise ValueError('An encrypted transfer must start at the beginning.')
        record = self._record
        return self._encrypted.fileno(), dict(source_remote=record['remote'],
            source_path=record['encrypted_path'], source_identity=record['identity'])


@contextmanager
def native_transfer(client, record, path, encrypted):
    from .crypt_stream import NativeSource
    source = NativeSource(client, record, path)
    with source.open(path) as stream:
        def transfer_source():
            source.version(path)
            if stream.closed or encrypted.closed or stream.tell() != 0:
                raise ValueError('Encrypted transfer source is closed or already consumed.')
            return encrypted.fileno(), dict(source_remote=record['remote'],
                source_path=record['encrypted_path'], source_identity=record['identity'])
        stream.transfer_source = transfer_source
        stream.crypt_transfer = True
        yield stream


class CryptFiles(LocalFiles):
    private = True

    def __init__(self, root, client, remote, *, namespace=None):
        self.client, self.remote = client, remote
        self.identity = client.request('crypt_path', remote=remote, path='', directory=True)['identity']
        if namespace is not None and (not isinstance(namespace, str) or len(namespace) != 64
                                      or any(c not in '0123456789abcdef' for c in namespace)):
            raise ValueError('Invalid encrypted storage namespace.')
        namespace = namespace or self.identity
        root = Path(root) / namespace
        if root.is_symlink() or root.parent.is_symlink():
            raise ValueError('Managed encrypted storage cannot use linked folders.')
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        super().__init__(root)
        self.storage_namespace = namespace

    def mapping(self, path, directory=False, decode=False):
        return self.client.request('crypt_path', remote=self.remote, identity=self.identity,
                                   path=self.relative(path), directory=directory, decode=decode)['path']

    def _physical(self, path, directory=False):
        path = self.relative(path)
        encoded = self.mapping(path, directory)
        return self.root / encoded if path else self.root

    def record(self, path):
        return dict(remote=self.remote, identity=self.identity, encrypted_path=self.mapping(path))

    def list(self, path='', *, cancelled=lambda: False):
        path = self.relative(path)
        rows = []
        for child in self._locate(path).iterdir():
            check_cancelled(cancelled)
            self._guard(child)
            plain = self.mapping(child.relative_to(self.root).as_posix(), child.is_dir(), decode=True)
            if plain.rpartition('/')[0] != path:
                raise ValueError('Invalid encrypted folder entry.')
            rows.append(self.entry(plain))
        return sorted(rows, key=lambda row: (not row['directory'], row['name'].casefold()))

    @contextmanager
    def open(self, path):
        record = self.record(path)
        with self._locate(path).open('rb') as encrypted:
            if getattr(self.client, 'supports_streaming', False):
                with native_transfer(self.client, record, self._locate(path), encrypted) as stream:
                    yield stream
                return
            result = self.client.request('crypt_raw_read', remote=self.remote, identity=self.identity,
                                         path=record['encrypted_path'], fd=encrypted.fileno())
            with CryptTransferStream(base64.b64decode(result['data'], validate=True), record, encrypted) as stream:
                yield stream

    def create_file(self, path, stream, *, cancelled=lambda: False):
        with mutation_lock:
            check_cancelled(cancelled)
            path = self.relative(path)
            if not path or self._locate(path).exists():
                raise FileExistsError('Destination already exists.')
            target = self._guard(self._physical(path))
            staged = '/'.join(p for p in (path.rpartition('/')[0], '.create-' + uuid4().hex + Path(path).suffix) if p)
            temporary = self._guard(self._physical(staged))
            values = {}
            if isinstance(stream, CryptTransferStream) or getattr(stream, 'crypt_transfer', False):
                if stream.closed or stream.tell() != 0:
                    raise ValueError('Encrypted transfers require an unconsumed open stream.')
                fd, values = stream.transfer_source()
            else:
                try:
                    fd = stream.fileno()
                except (OSError, AttributeError):
                    fd = None
            owned = False
            try:
                with temporary.open('xb') as output:
                    owned = True
                    if fd is None:
                        data = stream.read(1024 * 1024 + 1)
                        if len(data) > 1024 * 1024:
                            raise ValueError('Text saves are limited to 1 MiB.')
                        self.client.request('crypt_encode', remote=self.remote, identity=self.identity,
                                            path=self.mapping(path), fd=output.fileno(), data=base64.b64encode(data).decode())
                    else:
                        self.client.request('crypt_raw_write', remote=self.remote, identity=self.identity,
                                            path=self.mapping(path), fd=fd, output_fd=output.fileno(), **values)
                check_cancelled(cancelled)
                self.mapping(path)  # Revalidate the credential session before publication.
                rename_exclusive(temporary, target)
            finally:
                if owned:
                    temporary.unlink(missing_ok=True)


class ManagedCopies(LocalCryptCopies):
    """Reuse private reader/editor transactions for files in a managed tree."""
    def __init__(self, provider):
        self.provider = provider
        super().__init__(provider.root, provider.client)

    def _data(self, key):
        return self.provider._guard(self.provider._physical(key))

    def _temporary(self, key):
        staged = '/'.join(p for p in (key.rpartition('/')[0], '.save-' + uuid4().hex + Path(key).suffix) if p)
        return self.provider._guard(self.provider._physical(staged))

    def record(self, key):
        self.provider.entry(key)
        return self.provider.record(key)


class DownloadedCryptFile(LocalFiles):
    """One existing offline copy exposed as a movable resource, without migration."""
    private = True
    capabilities = ResourceCapabilities(rename=True, delete=True)

    def __init__(self, copies, key):
        self.copies, self.key = copies, key
        record = copies.record(key)
        name = copies.client.request('crypt_describe', remote=record['remote'], identity=record['identity'], path=record['encrypted_path'])
        self.name = Path(name).name
        super().__init__(copies._folder(key))

    def _physical(self, path, directory=False):
        if self.relative(path) != self.name:
            raise ValueError('Choose the downloaded file.')
        return self.copies._data(self.key)

    def record(self, path):
        self._physical(path)
        return self.copies.record(self.key)

    @contextmanager
    def open(self, path):
        self._physical(path)
        record = self.copies.record(self.key)
        with self.copies._data(self.key).open('rb') as encrypted:
            if getattr(self.copies.client, 'supports_streaming', False):
                with native_transfer(self.copies.client, record, self.copies._data(self.key), encrypted) as stream:
                    yield stream
                return
            result = self.copies.client.request('crypt_raw_read', remote=record['remote'], identity=record['identity'],
                                                path=record['encrypted_path'], fd=encrypted.fileno())
            with CryptTransferStream(base64.b64decode(result['data'], validate=True), record, encrypted) as stream:
                yield stream

    def rename(self, source, destination):
        from commonUtils.persistence import atomic_write_json
        with mutation_lock:
            self._physical(source)
            destination = self.relative(destination)
            if not destination:
                raise ValueError('A file name is required.')
            record = self.copies.record(self.key)
            result = self.copies.client.request('crypt_path', remote=record['remote'], identity=record['identity'], path=destination)
            record['encrypted_path'] = result['path']
            atomic_write_json(self.copies._folder(self.key) / 'record.json', record)
            self.name = Path(destination).name

    def remove_empty(self, path, revision):
        # Snapshot the record too: swapping its mapping invalidates the operation.
        super().remove_empty(path, revision)
        self.copies._folder(self.key).joinpath('record.json').unlink()
        self.copies._folder(self.key).rmdir()

    def entry(self, path):
        row = super().entry(path)
        row['revision'] = (row['revision'], self.copies._snapshot(self.key))
        return row


class TextReader:
    """Mobile presentation adapter for the shared text session."""
    editable = True
    book = None

    def __init__(self, name, data, *, key=None, revision=None):
        from commonUtils.persistence.text import TextSession
        self.session = TextSession(name, data, key=key, revision=revision, max_bytes=1024 * 1024)
        self.name, self.data, self.key, self.revision = name, data, key, revision
        self.kind = Path(name).suffix.lower()
        self.text_snapshot, self.text = self.session.text_snapshot, self.session.text
        self.labels = [name]

    def page(self, index):
        if index != 0:
            raise ValueError('Page does not exist.')
        return 'text', self.text


class LocalTextCopies:
    """Verified local text saves for an editor retargeted out of LocalCrypt."""
    encrypted = False

    def __init__(self, provider):
        self.provider = provider

    @property
    def offline(self):
        from commonUtils.runtime.local_files import LocalFiles
        return isinstance(self.provider, LocalFiles)

    def open(self, key, *, password='', cancelled=lambda: False):
        from commonUtils.runtime.resource_selection import ResourceTextSession
        session = ResourceTextSession.open(self.provider, key, cancelled=cancelled)
        return TextReader(session.text.name, session.text.data, key=session.path, revision=session.text.revision)

    def save(self, reader, text, *, cancelled=lambda: False):
        from commonUtils.runtime.resource_selection import ResourceTextSession
        session = ResourceTextSession(self.provider, reader.key, reader.session)
        updated = session.save(text, cancelled=cancelled)
        return TextReader(updated.text.name, updated.text.data, key=updated.path, revision=updated.text.revision)
