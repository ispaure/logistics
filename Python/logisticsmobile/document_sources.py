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
def opening_status(app, source, *, destination=None):
    """Present a temporary file panel, retaining the screen underneath it."""
    routes = getattr(app, 'routes', None)
    task = asyncio.current_task()
    pending = getattr(app, '_file_loading', None)
    if routes is None or (pending is not None and pending['task'] is task):
        yield
        return
    import toga
    from toga.style import Pack
    from toga.style.pack import COLUMN, CENTER
    from .browser_ui import BrowserStatusLabel, entry_icon
    name = Path(source.get('path') or source.get('key') or 'File').name
    label = BrowserStatusLabel(name, style=Pack(font_size=18, text_align=CENTER, margin_top=16))
    label.style.margin_left = label.style.margin_right = 0
    image = entry_icon(False)
    image.style.width = image.style.height = 64
    progress = toga.ProgressBar(max=None, style=Pack(height=6, margin_top=24))
    status = BrowserStatusLabel('Preparing document…', style=Pack(font_size=12, text_align=CENTER, margin_top=12))
    status.style.margin_left = status.style.margin_right = 0
    content = toga.Box(children=[image, label, progress, status],
                       style=Pack(direction=COLUMN, align_items=CENTER, margin=32))
    progress.style.align_self = 'stretch'
    panel = toga.Box(children=[toga.Box(style=Pack(flex=1)), content,
                               toga.Box(style=Pack(flex=1))],
                     style=Pack(direction=COLUMN, flex=1))
    destination = destination or app.native_host.state.destination
    route = 'file-loading:' + str(id(panel))
    state = dict(task=task, route=route, destination=destination, panel=panel, ready=False)
    app._file_loading = state
    # Loading is presentation, not a new user intent. Preserve the generation
    # used by provider readers to reject completion after navigation away.
    adaptive = app.adaptive
    split = adaptive.split is not None and destination == 'documents'
    if split:
        app.native_host.activate(destination)
        adaptive.present(panel, route=route, title=name)
    else:
        routes.show(panel, destination=destination, route=route, title=name)
    progress.start()
    from .loading_progress import OpeningProgress, current_progress
    reporter = OpeningProgress(app, state, progress, status)
    state['progress'] = reporter
    token = current_progress.set(reporter)
    try:
        yield
    finally:
        current_progress.reset(token)
        reporter.close()
        progress.stop()
        label.text = ''
        status.text = ''
        image.image = None
        if getattr(app, '_file_loading', None) is state:
            app._file_loading = None
        screens = adaptive.detail_routes if split else routes.screens[destination]
        if screens and screens[-1][0] == route:
            visible = app.native_host.state.destination == destination
            if split:
                adaptive.trim_details(len(screens) - 1)
                if visible and adaptive.in_detail:
                    if adaptive.detail_routes:
                        app.body = adaptive.detail_routes[-1][1]
                        app.route_changed(app.body)
                    else:
                        adaptive.show_list()
            else:
                routes.trim(destination, len(screens) - 1)
            if visible and not split:
                routes.render(destination)


async def opening_ready(app):
    state = getattr(app, '_file_loading', None)
    if state is None:
        await asyncio.sleep(0)
        return True
    if not state['ready']:
        from .draw_ready import wait_for_draw
        state['draw_acknowledged'] = await wait_for_draw(state['panel'])
        state['ready'] = True
    adaptive = app.adaptive
    split = adaptive.split is not None and state['destination'] == 'documents'
    screens = adaptive.detail_routes if split else app.routes.screens[state['destination']]
    return (getattr(app, '_file_loading', None) is state and app.active_host
            and app.native_host.state.destination == state['destination']
            and bool(screens) and screens[-1][0] == state['route'])


async def reopen_file(app, source):
    if source.get('type') == 'remote' and getattr(app, 'cloud_busy', False):
        from features.rclone.mobile.cloud_ui import explain_remote_busy
        await explain_remote_busy(app)
        return False
    with opening_status(app, source):
        if not await opening_ready(app):
            return False
        return await _reopen_file(app, source)


def local_document_path(app, path):
    """Recover iOS Documents references after an app container relocation."""
    path = Path(path)
    if path.exists():
        return path
    from features.rclone.mobile.storage_location import shared_documents_path
    root = shared_documents_path(getattr(app, 'private_root', Path('/')))
    if root is None:
        return path
    parts = path.parts
    # Only historical iOS application Documents paths can be relocated. Never
    # turn an arbitrary missing file into a same-named file in this app.
    prefix = ('/', 'var', 'mobile', 'Containers', 'Data', 'Application')
    if parts[:len(prefix)] != prefix or len(parts) < 9 or parts[7] != 'Documents':
        return path
    relative = Path(*parts[8:])
    if '..' in relative.parts:
        return path
    candidate = root / relative
    return candidate if candidate.is_file() else path


async def _reopen_file(app, source):
    """Resolve credentials again before constructing any encrypted provider."""
    if source['type'] == 'local':
        path = local_document_path(app, source['path'])
        if path.suffix.lower() in {'.pdf', '.epub', '.cbz', '.zip'}:
            return await app.open_download(path=path)
        from commonUtils.runtime.local_files import LocalFiles
        from features.text_editor.resources import LocalTextCopies
        return await app.open_crypt(copies=LocalTextCopies(LocalFiles(path.parent)), key=path.name)
    app.show_cloud(present=False)
    origin = getattr(app, 'navigation_generation', None)
    restore = getattr(app, 'cloud_restore_task', None)
    if restore is not None:
        await asyncio.shield(restore)
        if (not app.active_host or app.navigation_generation != origin):
            return False
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
    return await app.open_crypt(copies=copies, key=source['key'])


def folder_location(app, session, owner=None):
    """Resolve a live folder source without guessing paths for imported copies."""
    if session is None:
        return None
    manager = getattr(app, 'private_sessions', None)
    owner = owner or (manager.controllers.get(session.id) if manager else None)
    reader = getattr(owner, 'crypt_reader', None)
    copies = getattr(owner, '_crypt_reader_store', None)
    if reader is not None and copies is not None:
        provider = getattr(copies, 'provider', None)
        if provider is not None:
            if (provider.private and manager.controllers.get(session.id) is owner
                    and not manager.available(session.id)):
                return None
            return dict(provider=provider, key=reader.key)
        if (getattr(copies, 'remote_storage', False)
                and (manager.controllers.get(session.id) is not owner or manager.available(session.id))):
            return dict(remote=copies.remote, key=reader.key)
    source = (getattr(session, 'history_source', None) or getattr(session, 'source', None)
              or getattr(app, '_document_folder_sources', {}).get((session.provider, session.resource)))
    if source and source.get('type') == 'local':
        path = local_document_path(app, source['path'])
        if path.is_file():
            return dict(path=path)
    if session.provider == 'library':
        readers = getattr(app, 'readers', None)
        controller = getattr(readers, 'controllers', {}).get(session.id)
        store = getattr(owner or controller, 'library_store', None)
        if store is not None:
            suffix = '.cbz' if session.kind == 'comic' else '.epub'
            path = store.path(session.resource, suffix)
            if path.is_file():
                return dict(path=path)
    return None


def folder_action(app, session, owner=None):
    if folder_location(app, session, owner) is None:
        return []
    return [('Show in folder', lambda: show_in_folder(app, session, owner))]


async def show_in_folder(app, session, owner=None):
    location = folder_location(app, session, owner)
    if location is None or not app.checkpoint():
        return False
    # Capture the source before presenting Workspaces suspends private pixels.
    app.show_locations()
    remote = location.get('remote')
    # Back to the overview must retain the storage source of the revealed file.
    # LocalCrypt providers contain local ciphertext, even if bound to a remote.
    source = ('Network shares' if remote in app.network_share_remotes() else 'rclone') if remote else 'Local'
    app.change_folder_source(source)
    if 'remote' in location:
        app.show_cloud(present=False)
        if not await app.browser_cloud_location((location['remote'], location['key'].rpartition('/')[0])):
            return False
        app.show_cloud()
        browser = app.remote_browser
        key = location['key']
    else:
        provider = location.get('provider')
        path = location.get('path')
        if path is None and not getattr(provider, 'private', True):
            path = Path(provider.root) / location['key']
        if path is not None:
            await app.show_files()
            matching = []
            for label in app.ordinary_file_roots():
                candidate = app.file_provider_for(label)
                if not candidate.private and path.resolve().is_relative_to(Path(candidate.root).resolve()):
                    matching.append((len(Path(candidate.root).parts), label, candidate))
            if matching:
                _, label, provider = max(matching, key=lambda item: item[0])
                key = path.resolve().relative_to(Path(provider.root).resolve()).as_posix()
                if not await app.browser_file_location((label, key.rpartition('/')[0])):
                    return False
                browser = app.file_browser
            else:
                from commonUtils.runtime.local_files import LocalFiles
                provider, key = LocalFiles(path.parent), path.name
                drawer = app.adaptive.browser('files')
                if not await drawer.show_main_browser(path.parent.name, provider=provider):
                    return False
                browser = drawer.browser
        else:
            key = location['key']
            drawer = app.adaptive.browser('files')
            if not await drawer.show_main_browser(getattr(provider, 'remote', 'Encrypted files'),
                    folder=key.rpartition('/')[0], provider=provider):
                return False
            browser = drawer.browser
    entry = next((entry for entry in browser.entries if entry.payload['path'] == key), None)
    if entry is not None:
        await browser.select(entry)
    return True
