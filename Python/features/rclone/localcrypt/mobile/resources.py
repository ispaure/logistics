"""Local mobile folder providers; crypt naming/bytes stay in the native bridge."""
from features.rclone.mobile.storage_location import collection_path, _modified_time
from contextlib import contextmanager
from io import BytesIO
import base64
import os
import re
import stat
from pathlib import Path, PurePosixPath
from uuid import uuid4

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.provider import ResourceCapabilities
from commonUtils.persistence.publication import mutation_lock, rename_exclusive
from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.streams import read_up_to
from features.rclone.localcrypt.mobile.copies import LocalCryptCopies


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
    from features.rclone.localcrypt.mobile.archive_source import NativeSource
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

    def __init__(self, root, client, remote, *, namespace=None, storage_root=None, create=True):
        self.collection_storage_root = storage_root
        self.client, self.remote = client, remote
        self.identity = client.request('crypt_path', remote=remote, path='', directory=True)['identity']
        if namespace is not None and (not isinstance(namespace, str) or len(namespace) != 64
                                      or any(c not in '0123456789abcdef' for c in namespace)):
            raise ValueError('Invalid encrypted storage namespace.')
        namespace = namespace or self.identity
        root = Path(root) / namespace
        if root.is_symlink() or root.parent.is_symlink():
            raise ValueError('Managed encrypted storage cannot use linked folders.')
        if create:
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
        super().__init__(root)
        self.storage_namespace = namespace

    def _guard(self, path):
        if self.collection_storage_root is not None:
            expected = collection_path(self.collection_storage_root, True) / self.storage_namespace
            if expected != self.root:
                raise ValueError('Collection location changed. Restart Logistics.')
        return super()._guard(path)

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
        # Bound native requests while sharing the credential lookup and JSON
        # boundary across filenames. Keep plaintext names only in this snapshot.
        folder = self._locate(path)
        children = []
        with os.scandir(folder) as entries:
            for entry in entries:
                check_cancelled(cancelled)
                child = Path(entry.path)
                # _locate and the final guard validate the parent chain and
                # collection boundary. Direct children still reject links and
                # special/shared files without rewalking every ancestor.
                if entry.is_symlink() or (hasattr(Path, 'is_junction') and child.is_junction()):
                    raise ValueError('Linked storage is not supported.')
                try:
                    info = entry.stat(follow_symlinks=False)
                    directory = stat.S_ISDIR(info.st_mode)
                    if not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                        raise ValueError('Choose an independent regular file or folder.')
                    if re.fullmatch(r'.+\.[0-9a-f]{8}\.partial', child.name):
                        continue
                    children.append((child, info, directory))
                except FileNotFoundError:
                    continue
        for offset in range(0, len(children), 256):
            check_cancelled(cancelled)
            batch = children[offset:offset + 256]
            names = self.client.request('crypt_paths', remote=self.remote, identity=self.identity,
                # The parent path was already located and validated. Decode
                # each basename once, rather than its ancestors for every row.
                entries=[dict(path=child.name, directory=directory)
                         for child, _, directory in batch])
            if len(names) != len(batch):
                raise ValueError('Incomplete encrypted folder listing.')
            for plain, (child, info, directory) in zip(names, batch):
                check_cancelled(cancelled)
                plain = self.relative(plain)
                if not plain or '/' in plain:
                    raise ValueError('Invalid encrypted folder entry.')
                plain = '/'.join(part for part in (path, plain) if part)
                try:
                    current = child.stat(follow_symlinks=False)
                except FileNotFoundError:
                    continue  # A concurrent Pull retired this entry during decode.
                if (current.st_dev, current.st_ino, current.st_mode) != (info.st_dev, info.st_ino, info.st_mode):
                    continue
                if not directory and current.st_nlink != 1:
                    continue
                info = current
                revision = ((info.st_dev, info.st_ino) if directory else
                    (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns))
                rows.append(dict(name=PurePosixPath(plain).name, path=plain, directory=directory,
                    size=info.st_size, revision=revision,
                    modified=_modified_time(info.st_mtime)))
        check_cancelled(cancelled)
        self._guard(folder)
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

    def archive_password(self, path, *, cancelled=lambda: False):
        from services.documents.zip_passwords import password_from_ini
        relative = PurePosixPath(self.relative(path))
        for folder in (relative.parent, *relative.parent.parents):
            check_cancelled(cancelled)
            candidate = str(folder / 'remoteConfig.ini')
            try:
                with self.open(candidate) as stream:
                    data = stream.read(65537)
            except FileNotFoundError:
                continue
            password, found = password_from_ini(data)
            if found:
                return password
        return None

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
                        data = read_up_to(stream, 1024 * 1024 + 1, cancelled=cancelled)
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

    def open(self, key, *, password='', cancelled=lambda: False):
        from commonUtils.archives.zip_access import ArchivePasswordError
        try:
            return super().open(key, password=password, cancelled=cancelled)
        except ArchivePasswordError:
            if password:
                raise
            configured = self.provider.archive_password(key, cancelled=cancelled)
            if not configured:
                raise
            return super().open(key, password=configured, cancelled=cancelled)

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


def encrypted_storage(root, client, remote, *, create=True):
    """Resolve an unscoped encrypted location without leaking its layout to hosts."""
    return CryptFiles(collection_path(Path(root), True), client, remote, storage_root=root, create=create)


def encrypted_copies(provider):
    return ManagedCopies(provider)


def encrypted_document(provider, path):
    """Return the feature-owned reader store/key, or defer to ordinary hosting."""
    if isinstance(provider, DownloadedCryptFile):
        return provider.copies, provider.key
    if isinstance(provider, CryptFiles):
        return encrypted_copies(provider), path
    return None


def encrypted_library_sources(root, jobs, client, remotes):
    """Contribute unlocked encrypted collection roots to the generic catalogue."""
    from features.rclone.transfers.mobile.jobs import copy_target, resolved_job
    sources, failures = [], 0
    if client is None:
        return sources, failures
    root = Path(root)
    for remote in remotes:
        try:
            identity = client.request('crypt_path', remote=remote, path='', directory=True)['identity']
            if (collection_path(root, True) / identity).is_dir():
                sources.append((encrypted_storage(root, client, remote), '', 'LocalCrypt: ' + remote))
            for job in jobs:
                job = resolved_job(client, job)
                if (not job['crypt'] or job['remote'] != remote
                        or client.connection_identity(remote) != job['identity']):
                    continue
                physical = copy_target(root, job)
                if not physical.is_dir() or physical.is_symlink():
                    continue
                provider = CryptFiles(collection_path(root, True), client, remote, namespace=job['identity'], storage_root=root)
                folder = provider.mapping(job['prefix'], directory=True, decode=True)
                sources.append((provider, folder, 'LocalCrypt: ' + remote))
        except (OSError, ValueError):
            failures += 1
    return sources, failures
