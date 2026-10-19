"""Source badges and credential-bound reopen references for mobile documents."""
import asyncio
from contextlib import contextmanager
from pathlib import Path


def saved_connection(app, remote, identity):
    """Only the matching saved connection allows plaintext durable history."""
    client = app.cloud_client
    for record in getattr(client, 'package_records', ()):
        if remote in record.get('remotes', ()):
            identities = (*record.get('identities', {}).values(),
                          *record.get('crypt_identities', {}).values())
            return bool(record.get('saved') and identity in identities)
    return False


def file_source(app, copies, key, *, session_only=False):
    provider = getattr(copies, 'provider', None)
    if not getattr(copies, 'encrypted', True):
        root = getattr(provider, 'root', getattr(copies, 'root', None))
        return dict(type='local', path=str(Path(root) / key)) if root is not None else None
    if getattr(copies, 'remote_storage', False):
        remote = copies.remote
        identity = copies.client.connection_identity(remote)
        source = dict(type='remote', remote=remote, identity=identity, key=key)
    elif provider is not None and hasattr(provider, 'remote'):
        source = dict(type='crypt', remote=provider.remote, identity=provider.identity, key=key, namespace=provider.storage_namespace)
    else:
        record = copies.record(key)
        source = dict(type='download', remote=record['remote'], identity=record['identity'], key=key)
    return source if session_only or saved_connection(app, source['remote'], source['identity']) else None


def session_source(app, session):
    if session.provider == 'file-reference':
        return getattr(session, 'source', None)
    if session.provider == 'credential-reference':
        return session.cache_source
    manager = getattr(app, 'private_sessions', None)
    owner = manager.controllers.get(session.id) if manager else None
    if owner is not None:
        store = getattr(owner, '_crypt_reader_store', None)
        if getattr(store, 'remote_storage', False):
            return dict(type='remote')
        if getattr(store, 'encrypted', True):
            return dict(type='crypt')
    return dict(type='local')


def source_icons(app, session):
    source = session_source(app, session) or dict(type='local')
    kind = source['type']
    if kind == 'local':
        return [('storage_local', 'Local file')]
    icons = [('storage_remote', 'Cloud file')] if kind == 'remote' else [('storage_local', 'Local encrypted file')]
    unlocked = False
    if session.provider == 'provider-session':
        unlocked = app.private_sessions.available(session.id)
    elif source.get('remote'):
        client = getattr(app, 'cloud_client', None)
        try:
            cipher = source['type'] in {'crypt', 'download'}
            remote = client.resolve_remote(source['remote'], source['identity'], cipher=True) if cipher and hasattr(client, 'resolve_remote') else (
                client.resolve_remote(source['remote'], source['identity']) if hasattr(client, 'resolve_remote') else source['remote'])
            # Badge rendering runs on the UI thread. Credential publication
            # already supplies fingerprints; never wait on the native bridge
            # once per row while an unrelated network operation holds its lock.
            field = 'crypt_identities' if cipher else 'identities'
            unlocked = any(record.get(field, {}).get(remote) == source['identity']
                           for record in getattr(client, 'package_records', ()))
        except (OSError, ValueError, AttributeError):
            pass
    icons.append(('storage_unlocked' if unlocked else 'storage_crypt',
                  'Connection unlocked' if unlocked else 'Unlock connection to open'))
    return icons


@contextmanager
def opening_status(app, source):
    """Show quiet activity below the current view until a source has reopened."""
    body = getattr(app, 'body', None)
    if body is None:
        yield
        return
    import toga
    from toga.style import Pack
    from toga.style.pack import COLUMN
    from .appearance import surface
    message = 'Opening cloud file…' if source['type'] == 'remote' else 'Opening file…'
    label = toga.Label(message, style=Pack(font_size=12, margin_left=12, margin_right=12))
    surface(label, radius=0, background='transparent', foreground='muted',
            outlined=False, eink_outlined=False)
    progress = toga.ProgressBar(max=None, style=Pack(height=3, margin_top=2))
    banner = toga.Box(children=[label, progress], style=Pack(direction=COLUMN))
    body.add(banner)
    progress.start()
    try:
        yield
    finally:
        progress.stop()
        # Navigation may already have detached the originating view. Never
        # restore it or touch the newly selected document when the read ends.
        if banner.parent is not None:
            banner.parent.remove(banner)


async def reopen_file(app, source):
    with opening_status(app, source):
        # Let native controls paint before credential resolution or file I/O.
        await asyncio.sleep(0)
        return await _reopen_file(app, source)


async def _reopen_file(app, source):
    """Resolve credentials again before constructing any encrypted provider."""
    if source['type'] == 'local':
        path = Path(source['path'])
        if path.suffix.lower() in {'.pdf', '.epub', '.cbz', '.zip'}:
            return await app.open_download(path=path, destination='documents')
        from commonUtils.runtime.local_files import LocalFiles
        from features.text_editor.resources import LocalTextCopies
        return await app.open_crypt(copies=LocalTextCopies(LocalFiles(path.parent)), key=path.name,
                                    destination='documents')
    app.show_cloud(present=False)
    remote, identity = source['remote'], source['identity']
    async def resume():
        return await reopen_file(app, source)
    cipher = source['type'] in {'crypt', 'download'}
    client = getattr(app, 'cloud_client', None)
    if cipher:
        if hasattr(client, 'resolve_remote'):
            remote = client.resolve_remote(remote, identity, cipher=True)
        try:
            ready = client.request('crypt_path', remote=remote, path='', directory=True)['identity'] == identity
        except (OSError, ValueError, AttributeError):
            ready = False
        if not ready and not await app.require_remote_credentials_async(remote, resume=resume):
            return False
    elif not await app.require_remote_credentials_async(remote, identity=identity, resume=resume):
        return False
    if hasattr(client, 'resolve_remote'):
        remote = client.resolve_remote(remote, identity, cipher=True) if cipher else client.resolve_remote(remote, identity)
    if source['type'] == 'remote':
        from features.rclone.mobile.remote_readers import RemoteReaders
        copies = RemoteReaders(client, remote)
    elif source['type'] == 'crypt':
        from features.rclone.localcrypt.mobile.resources import CryptFiles, ManagedCopies
        from features.rclone.mobile.storage_location import collection_path
        copies = ManagedCopies(CryptFiles(collection_path(app.private_root, True), client, remote,
            namespace=source['namespace'], storage_root=app.private_root, create=False))
        if copies.provider.identity != identity:
            raise ValueError('The encrypted file connection changed.')
    else:
        copies = app.crypt_copies
        if copies.record(source['key'])['identity'] != identity:
            raise ValueError('The downloaded file connection changed.')
    return await app.open_crypt(copies=copies, key=source['key'], destination='documents')
