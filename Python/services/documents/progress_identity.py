"""Document lookup identity, independent of navigation and access grants."""

import os
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

from commonUtils.filesystem.local_access import check_local_path
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.paths import resource_path

from .credential_state import credential_authority, sources
from .locations import collection_path, selection, shared_documents_path


def local_document_path(private_root, path):
    """Recover an old iOS Documents reference only if its replacement exists."""
    original = Path(path)
    if original.is_absolute() and original.exists():
        return original
    documents = shared_documents_path(private_root)
    if documents is None:
        return original
    parts = PurePosixPath(path).parts
    if parts[:3] == ('/', 'private', 'var'):
        parts = ('/', *parts[2:])
    prefix = ('/', 'var', 'mobile', 'Containers', 'Data', 'Application')
    if parts[:len(prefix)] != prefix or len(parts) < 9 or parts[7] != 'Documents':
        return original
    relative = Path(*parts[8:])
    if relative.anchor or '..' in relative.parts:
        return original
    candidate = documents / relative
    if candidate.is_file() and candidate.resolve().is_relative_to(documents.resolve()):
        return candidate
    return original


def _local_full_path(provider, path, private_root):
    if provider is None:
        original = Path(path)
        if original.is_absolute():
            check_local_path(original)
        full = local_document_path(private_root, path) if private_root else original
        if not full.is_absolute():
            raise ValueError('A local document requires an absolute path.')
        check_local_path(full)
        return full.resolve()
    key = Path(path) if Path(path).is_absolute() else path
    return provider.transfer_location(key)


def _local_identity(provider, path, private_root, managed_roots):
    full = _local_full_path(provider, path, private_root)
    roots = []
    if private_root is not None:
        documents = shared_documents_path(private_root)
        if documents is not None:
            roots.append(('app:ios-documents', documents))
        try:
            local = collection_path(private_root)
            selected = selection(private_root)
        except (OSError, ValueError):
            # An unavailable collection drive need not hide other admitted files.
            local = None
        if local is not None and documents is None:
            scope = 'app' if selected is None else 'drive:' + selected['token']
            roots.extend(((scope + ':local', local), (scope + ':received', local.parent / 'Received Files')))
    roots.extend((f'registered:{name}', Path(root)) for name, root in (managed_roots or {}).items())
    resolved = [(root.resolve(), name) for name, root in roots]
    matches = [(root, name) for root, name in resolved if root in full.parents]
    if matches:
        root, name = max(matches, key=lambda item: (len(item[0].parts), item[1]))
        return ('local', name, os.path.normcase(full.relative_to(root).as_posix()))
    return ('local', 'absolute', os.path.normcase(str(full)))


def _protected(chain):
    for source in chain:
        capabilities = getattr(source, 'document_capabilities', None)
        if (getattr(source, 'private', False) or getattr(source, 'remote_storage', False)
                or getattr(capabilities, 'private', False) or getattr(capabilities, 'credential_bound', False)
                or getattr(capabilities, 'remote', False)
                or (getattr(source, 'client', None) is not None and getattr(source, 'remote', None))):
            return True
    return False


def ordinary_local_provider(provider):
    chain = tuple(sources(provider))
    if not _protected(chain):
        return next((source for source in chain if isinstance(source, LocalFiles)), None)


def stable_remote_name(provider):
    """Use the package's original remote name across temporary native aliases."""
    for source in sources(provider):
        remote = getattr(source, 'remote', None)
        if not remote:
            continue
        client = getattr(source, 'client', None)
        for record in getattr(client, 'package_records', ()):
            for original, alias in record.get('aliases', {}).items():
                if remote == alias:
                    return original
        return remote
    return ''


def _protected_provider(chain, path):
    """Offline copies use their own stable copy key and never the remote key."""
    for source in chain:
        if getattr(source, 'copies', None) is not None and getattr(source, 'key', None):
            return SimpleNamespace(client=source.client, remote=source.remote, identity=source.identity,
                                   storage_namespace='offline-copy'), resource_path(source.key), 'offline-copy'
        if (getattr(source, 'client', None) is not None
                and getattr(source, 'remote', None) is None
                and getattr(getattr(source, 'document_capabilities', None), 'credential_bound', False)
                and callable(getattr(source, 'record', None))):
            try:
                record = source.record(path)
            except (OSError, ValueError):
                # Session lookup precedes admission. Let the copy owner report
                # its missing or invalid record, with no durable authority.
                return source, str(path), 'offline-copy-unavailable'
            return SimpleNamespace(client=source.client, remote=record['remote'],
                                   identity=record['identity'], storage_namespace='offline-copy'), resource_path(path), 'offline-copy'
    resource = next((source for source in reversed(chain)
                     if callable(getattr(source, 'relative', None))), None)
    if resource is not None:
        path = Path(path) if Path(path).is_absolute() else path
    logical = resource_path(resource.relative(path) if resource is not None else path)
    if not logical:
        raise ValueError('A reader requires a document key.')
    namespace = next((str(source.storage_namespace) for source in chain
                      if getattr(source, 'storage_namespace', None)), '')
    domain = 'remote' if any(getattr(source, 'remote_storage', False) for source in chain) else 'private'
    return chain[0], logical, (domain, namespace)


def progress_source(provider, path, *, app=None, private_root=None, managed_roots=None):
    """Return canonical identity and the backing encrypted provider/key, if any."""
    if private_root is None and app is not None:
        private_root = getattr(app, 'private_root', None)
    if private_root is not None:
        private_root = Path(private_root)
    chain = tuple(sources(provider))
    if not _protected(chain):
        local = next((source for source in chain if isinstance(source, LocalFiles)), None)
        if local is not None or provider is None:
            return _local_identity(local, path, private_root, managed_roots), None, None
        # Unknown providers have no authority to save into ordinary storage.
        return ('session', id(provider), str(path)), None, None

    protected, logical, namespace = _protected_provider(chain, path)
    authority = next((source.identity for source in sources(protected)
                      if getattr(source, 'client', None) is not None
                      and isinstance(getattr(source, 'identity', None), str)), None)
    if authority is None:
        try:
            authority = credential_authority(protected)
        except (OSError, ValueError, RuntimeError):
            authority = ('session', id(provider))
    return ('protected', authority, namespace, stable_remote_name(protected), logical), protected, logical


def document_identity(provider, path, *, app=None, managed_roots=None):
    """Lookup key for a document already admitted by the owning access policy."""
    return progress_source(provider, path, app=app, managed_roots=managed_roots)[0]


def external_file_identity(provider, path, fingerprint):
    """Physical identity for legacy video behavior across external same-file renames."""
    from stat import S_ISREG

    if (not isinstance(fingerprint, str) or len(fingerprint) != 64
            or any(character not in '0123456789abcdef' for character in fingerprint)):
        raise ValueError('A verified content fingerprint is required to follow an external rename.')
    full = _local_full_path(ordinary_local_provider(provider), path, None)
    info = full.stat()
    if not S_ISREG(info.st_mode) or not info.st_ino or info.st_nlink != 1:
        return None
    created = getattr(info, 'st_birthtime_ns', None)
    if created is None:
        created = getattr(info, 'st_birthtime', info.st_mtime_ns)
    return ('local', 'same-file', info.st_dev, info.st_ino, created, fingerprint)
