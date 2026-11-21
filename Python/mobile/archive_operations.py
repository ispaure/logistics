"""Archive operations on guarded, ordinary mobile file resources."""
from dataclasses import dataclass
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from commonUtils import archives
from commonUtils.filesystem.local_access import check_local_path
from commonUtils.persistence.publication import mutation_lock, rename_exclusive
from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.mutations import inventory
from commonUtils.runtime.resources.paths import resource_name, resource_path
from commonUtils.runtime.resources.provider import capabilities
from commonUtils.runtime.streams import copy_stream, stream_signature

FORMATS = {'zip': '.zip', 'tar': '.tar', 'tar.gz': '.tar.gz', 'tar.xz': '.tar.xz'}
ACTION_KINDS = {'archive-create', 'archive-extract', 'archive-add'}


def ordinary(provider):
    return (isinstance(provider, LocalFiles) and not provider.private
            and provider.storage_namespace == 'local' and not getattr(provider, 'remote_storage', False)
            and not getattr(provider, 'session_only', False)
            and type(provider)._physical is LocalFiles._physical)


def archive_name(name, format):
    suffix = FORMATS[format]
    name = resource_name(name)
    return name if name.lower().endswith(suffix) else name + suffix


def require_writable(path):
    if not path.stat().st_mode & 0o222 or not os.access(path, os.W_OK):
        raise PermissionError('This location is read-only.')


def physical(provider, path):
    if not ordinary(provider):
        raise ValueError('Choose an ordinary on-device file or folder.')
    return provider._locate(resource_path(path))


@dataclass(frozen=True)
class ArchiveItem:
    provider: object
    path: str
    revision: object = None

    @classmethod
    def from_row(cls, provider, row):
        return cls(provider, row['path'], row.get('revision'))

    def resolve(self, *, write=False):
        path = physical(self.provider, self.path)
        entry = self.provider.entry(self.path)
        if self.revision is not None and entry['revision'] != self.revision:
            raise ValueError('This item changed. Reopen it before continuing.')
        if write:
            if not capabilities(self.provider).replace:
                raise PermissionError('This archive is read-only.')
            require_writable(path)
            require_writable(path.parent)
        return path

    def resolve_source(self, cancelled):
        check_cancelled(cancelled)
        if not resource_path(self.path):
            raise ValueError('Select a file or folder inside the storage location.')
        path = self.resolve()
        check_local_path(path, recursive=True)
        if path.is_dir():
            # Apply the resource provider's descendant checks before the shared
            # archive engine opens a folder by its physical path.
            inventory(self.provider, self.path, cancelled=cancelled)
        return path

    def inspect(self, cancelled):
        path = self.resolve()
        if not path.is_file() or not archives.is_supported_archive(path):
            raise ValueError('Choose a supported archive file.')
        item = self.from_row(self.provider, self.provider.entry(self.path))
        members = archives.entries(path, cancelled=cancelled)
        item.resolve()
        return item, members

    def edit(self, cancelled, *, sources=(), remove=(), password=None):
        with mutation_lock:
            path = self.resolve(write=True)
            if not archives.is_zip_archive(path):
                raise ValueError('Only ZIP and CBZ archives can be edited.')
            additions = tuple(item.resolve_source(cancelled) for item in sources)
            if any(source == path or source in path.parents for source in additions):
                raise ValueError('An archive cannot contain itself.')
            archives.update_zip(path, sources=additions, remove=remove, password=password, cancelled=cancelled)
            return self.from_row(self.provider, self.provider.entry(self.path))


def output_path(provider, folder, name):
    parent = physical(provider, folder)
    if not parent.is_dir():
        raise ValueError('Choose an existing destination folder.')
    if not capabilities(provider).create:
        raise PermissionError('This destination is read-only.')
    require_writable(parent)
    relative = '/'.join(filter(None, (folder, resource_name(name))))
    destination = physical(provider, relative)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('An item already exists at the destination.')
    return destination


def create_archive(sources, provider, folder, name, format, work_root, cancelled, *, password=None):
    with mutation_lock:
        check_cancelled(cancelled)
        name = archive_name(name, format)
        target = output_path(provider, folder, name)
        paths = tuple(item.resolve_source(cancelled) for item in sources)
        parent = target.parent.stat()
        parent_id = parent.st_dev, parent.st_ino
        if any(target == source or source in target.parents for source in paths):
            raise ValueError('Choose a destination outside the selected items.')
        # Android shared storage can reject hard links. Build and verify on
        # internal storage, then verify a sibling copy before exclusive rename.
        with TemporaryDirectory(prefix='.logistics-archive-', dir=work_root) as temp:
            staged = Path(temp) / name
            archives.create(paths, staged, format=format, password=password, cancelled=cancelled)
            with TemporaryDirectory(prefix='.logistics-publish-', dir=target.parent) as sibling:
                delivered = Path(sibling) / 'archive'
                with staged.open('rb') as source, delivered.open('xb') as output:
                    copy_stream(source, output, cancelled=cancelled)
                    output.flush()
                    os.fsync(output.fileno())
                with staged.open('rb') as source, delivered.open('rb') as output:
                    if stream_signature(source, cancelled=cancelled) != stream_signature(output, cancelled=cancelled):
                        raise ValueError('Archive copy could not be verified.')
                for item in sources:
                    item.resolve()
                current = output_path(provider, folder, name).parent.stat()
                if (current.st_dev, current.st_ino) != parent_id:
                    raise ValueError('The destination changed.')
                check_cancelled(cancelled)
                rename_exclusive(delivered, target)
        return target


def extract_archive(item, provider, folder, name, cancelled, *, selected=None, password=None):
    with mutation_lock:
        path = item.resolve()
        target = output_path(provider, folder, name)
        check_local_path(target, recursive=True)
        return archives.extract(path, target, selected=selected, password=password, cancelled=cancelled)
