"""Mobile favourite references, retaining the viewer or Notes Library context."""
import asyncio
from pathlib import Path
from types import SimpleNamespace
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from services.documents.catalog import DocumentCatalog
from services.documents.credential_state import MobileCredentialCipher


def catalog(app):
    return DocumentCatalog(app.private_root)


def unlocked_ciphers(app):
    client = getattr(app, 'cloud_client', None)
    for record in getattr(client, 'package_records', ()):
        if record.get('saved') or not record.get('document_cache_id'):
            continue
        for field in ('identities', 'crypt_identities'):
            values = record.get(field, {})
            if values:
                remote, identity = next(iter(values.items()))
                yield MobileCredentialCipher(SimpleNamespace(client=client, remote=remote, identity=identity), app)
                break


def reference(app, host=None):
    from .document_sources import file_source, saved_connection
    session = getattr(host, 'session', None) or app.workspace.sessions.get(app.workspace.active)
    if session is None:
        raise ValueError('Open a file before adding it to favourites.')
    notes = getattr(app, 'vault_browser', None)
    cipher = None
    if notes is not None and notes.session is session:
        if notes.path is None or not notes.valid():
            raise ValueError('Choose a note first.')
        from services.documents.provider_documents import ProviderDocuments
        source = file_source(app, ProviderDocuments(notes.provider), notes.path, session_only=True)
        opener = dict(kind='notes', root=str(notes.provider.root / notes.root)
                      if source['type'] == 'local' else notes.root)
        provider = notes.provider
        title = Path(notes.path).name
    else:
        owner = app.private_sessions.controllers.get(session.id)
        provider = getattr(owner, '_crypt_reader_store', None)
        source = file_source(app, provider, owner.crypt_reader.key, session_only=True) if owner is not None else getattr(session, 'history_source', None)
        opener, title = dict(kind=session.kind), session.title
        if source is None:
            if session.transient:
                raise ValueError('This file has no saved opening reference yet.')
            source = dict(type='session', provider=session.provider, resource=session.resource)
    if source is None:
        raise ValueError('This file has no saved opening reference yet.')
    if source['type'] == 'local':
        source = dict(source, path=str(Path(source['path']).resolve()))
        if opener.get('kind') == 'notes':
            opener = dict(opener, root=str(Path(opener['root']).resolve()))
    if source['type'] not in {'local', 'session'} and not saved_connection(app, source['remote'], source['identity']):
        if provider is None:
            provider = SimpleNamespace(client=app.cloud_client, remote=source['remote'], identity=source['identity'])
        cipher = MobileCredentialCipher(provider, app)
        cipher.identity
    return source, title, opener, cipher


async def favourite(app, host=None):
    try:
        source, title, opener, cipher = reference(app, host)
        await asyncio.to_thread(catalog(app).remember, source, title, opener, favourite=True, cipher=cipher)
        app._favourites_version = getattr(app, '_favourites_version', 0) + 1
        for destination in ('home', 'documents'):
            app.refresh_hub(destination)
    except (OSError, ValueError, PermissionError) as error:
        await app.main_window.dialog(toga.InfoDialog('Favourite file', str(error)))


async def favourite_resource(app, provider, path, *, kind):
    from services.documents.provider_documents import ProviderDocuments
    from .document_sources import file_source, saved_connection
    source = file_source(app, ProviderDocuments(provider), path, session_only=True)
    if source is None:
        raise ValueError('This file has no reusable storage reference.')
    cipher = None
    if source['type'] == 'local':
        source = dict(source, path=str(Path(source['path']).resolve()))
    elif not saved_connection(app, source['remote'], source['identity']):
        cipher = MobileCredentialCipher(provider, app)
        cipher.identity
    await asyncio.to_thread(catalog(app).remember, source, Path(path).name,
                            dict(kind=kind), favourite=True, cipher=cipher)
    app._favourites_version = getattr(app, '_favourites_version', 0) + 1
    app.refresh_hub('home')


async def reopen(app, row):
    source, opener = row['source'], row['opener']
    try:
        if source['type'] == 'session':
            from .workspace import Session
            session = Session('', source['provider'], source['resource'], opener['kind'], title=row['title'])
            return await app.recent_opener(session)()
        if opener.get('kind') != 'notes':
            from .document_sources import reopen_file
            return await reopen_file(app, source, kind=opener.get('kind'))
        provider = None
        if source['type'] == 'local':
            from commonUtils.runtime.resources.local import LocalFiles
            path = Path(source['path'])
            library_root = Path(opener['root'])
            provider, path = LocalFiles(library_root), path.relative_to(library_root).as_posix()
        elif source['type'] == 'crypt':
            from features.rclone.mobile.service import native_service
            from features.rclone.localcrypt.mobile.locations import LocalCryptLocation
            from services.documents.locations import collection_path
            provider = native_service(app.cloud_client).localcrypt.open(LocalCryptLocation(
                collection_path(app.private_root, True), source['remote'], namespace=source['namespace'],
                storage_root=app.private_root, create=False, cipher_identity=source['identity']))
            path = source['key']
        else:
            raise ValueError('Notes Library requires Local or LocalCrypt storage.')
        try:
            from .obsidian import open_vault
            root = '' if source['type'] == 'local' else opener['root']
            owner = await open_vault(app, provider, root, 'documents')
            if owner is not None:
                return await owner.open_note(path)
        finally:
            if hasattr(provider, 'close'):
                provider.close()
    except (OSError, ValueError, PermissionError) as error:
        await app.main_window.dialog(toga.InfoDialog('Open favourite', str(error)))
    return False


def populate(app, container):
    container.add(toga.Label('Favourites', style=Pack(font_size=20, font_weight='bold', margin_top=12)))
    try:
        rows = catalog(app).entries(ciphers=list(unlocked_ciphers(app)))
    except (OSError, ValueError, PermissionError):
        rows = []
    for row in rows:
        async def open_row(widget=None, row=row, **kwargs):
            await reopen(app, row)
        async def remove(widget=None, row=row, **kwargs):
            try:
                cipher = next((value for value in unlocked_ciphers(app)
                    if any(item['id'] == row['id'] for item in catalog(app).read(value)['favourites'])), None)
                await asyncio.to_thread(catalog(app).remove, row['id'], cipher=cipher)
                app._favourites_version = getattr(app, '_favourites_version', 0) + 1
                app.refresh_hub('home')
                app.refresh_hub('documents')
            except (OSError, ValueError, PermissionError) as error:
                await app.main_window.dialog(toga.InfoDialog('Remove favourite', str(error)))
        container.add(toga.Box(children=[
            toga.Button(row['title'], on_press=open_row, style=Pack(height=48, flex=1)),
            toga.Button('Remove', on_press=remove, style=Pack(height=48)),
        ], style=Pack(direction=ROW)))
    if not rows:
        container.add(toga.Label('No favourite files.', style=Pack(margin_bottom=8)))
