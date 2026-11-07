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
            panel = getattr(app, '_notebook_views', {}).get(session.id) or app.text_views.get(session.id)
            document = getattr(panel, 'document', None)
            resource = getattr(document, 'resource', None)
            if resource is not None:
                from services.documents.provider_documents import ProviderDocuments
                provider = resource.provider
                source = file_source(app, ProviderDocuments(provider), resource.path, session_only=True)
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
    source, cipher = resource_reference(app, provider, path)
    await asyncio.to_thread(catalog(app).remember, source, Path(path).name,
                            dict(kind=kind), favourite=True, cipher=cipher)
    app._favourites_version = getattr(app, '_favourites_version', 0) + 1
    app.refresh_hub('home')
    app.refresh_hub('documents')


def resource_reference(app, provider, path, *, require_cipher=True):
    from services.documents.mobile_storage import document_source
    from .document_sources import file_source, saved_connection
    copies, key = document_source(provider, path)
    source = file_source(app, copies, key, session_only=True)
    if source is None:
        raise ValueError('This file has no reusable storage reference.')
    cipher = None
    if source['type'] == 'local':
        source = dict(source, path=str(Path(source['path']).resolve()))
    elif not saved_connection(app, source['remote'], source['identity']):
        cipher = MobileCredentialCipher(provider, app)
        try:
            cipher.identity
        except PermissionError:
            if require_cipher:
                raise
            cipher = None
    return source, cipher


def relocate(app, provider, source, destination=None):
    from .document_sources import saved_connection
    old_name, new_name = Path(source).name, Path(destination).name if destination is not None else ''
    source, cipher = resource_reference(app, provider, source, require_cipher=False)
    target = resource_reference(app, provider, destination, require_cipher=False)[0] if destination is not None else None
    # Offline single-file copies have a stable record key. Rename their display
    # title without changing that key or replacing a custom favourite label.
    names = (old_name, new_name) if source == target else None
    def update_history():
        from services.documents.catalog import relocated_source, relocated_title, relocated_opener
        notes = getattr(app, 'vault_browser', None)
        if notes is not None:
            retained = []
            for session in notes.recent_notes:
                before = session.source
                after = relocated_source(before, source, target)
                if after is None:
                    continue
                if after is not before:
                    session.source = after
                    session.resource = app.recent_documents.reference_id(after)
                    session.title = relocated_title(session.title, before, after, names=names)
                    session.history_opener = relocated_opener(session.history_opener, source, target)
                retained.append(session)
            notes.recent_notes = retained
        failed = False
        for owner in (app.recent_documents, app.credential_document_lists):
            try:
                owner.relocate(source, target, names=names)
            except (OSError, ValueError, PermissionError):
                failed = True
        app._favourites_version = getattr(app, '_favourites_version', 0) + 1
        if failed:
            app.recovery_notice.text = 'Files changed; some saved references could not be updated.'
    try:
        # A passwordless session cannot have a credential-encrypted favourite
        # bucket. Never fall back to writing private references in plaintext.
        if source['type'] == 'local' or cipher is not None or saved_connection(app, source['remote'], source['identity']):
            catalog(app).relocate(source, target, cipher=cipher, names=names)
    finally:
        # History objects and their coalesced writes belong to the UI loop.
        # Reconcile them even when a separate favourite catalog is unreadable.
        if app.loop.is_running():
            app.loop.call_soon_threadsafe(update_history)
        else:
            update_history()


async def reopen(app, row, *, error_title='Open favourite'):
    source, opener = row['source'], row['opener']
    try:
        if source['type'] == 'session':
            from .workspace import Session
            session = Session('', source['provider'], source['resource'], opener['kind'], title=row['title'])
            return await app.recent_opener(session)()
        if opener.get('kind') != 'notes':
            from .document_sources import reopen_file
            return await reopen_file(app, source, kind=opener.get('kind'))
        current = getattr(app, 'vault_browser', None)
        if current is not None and current.valid():
            if source['type'] == 'local':
                same = ((current.provider.root / current.root).resolve() == Path(opener['root']).resolve()
                        and not getattr(current.provider, 'private', False))
                path = Path(source['path']).relative_to(current.provider.root).as_posix() if same else None
            else:
                same = (source['type'] == 'crypt' and current.root == opener['root']
                        and getattr(current.provider, 'identity', None) == source['identity']
                        and getattr(current.provider, 'storage_namespace', None) == source['namespace']
                        and getattr(current.provider, 'remote', None) == source['remote'])
                path = source.get('key')
            if same:
                if not app.checkpoint():
                    return False
                opened = await current.open_note(path)
                if opened:
                    current.present()
                return bool(opened)
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
        await app.main_window.dialog(toga.InfoDialog(error_title, str(error)))
    return False


def populate(app, container, *, heading=True, row_font=None):
    if heading:
        container.add(toga.Label('Favourites', style=Pack(font_size=20, font_weight='bold', margin_top=12)))
    try:
        store = catalog(app)
        rows = store.entries(ciphers=list(unlocked_ciphers(app)), strict=False)
    except (OSError, ValueError, PermissionError):
        rows = []
    if 'store' in locals() and store.errors:
        container.add(toga.Label(store.errors[0], style=Pack(font_size=12)))
    buttons = []
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
        opener = toga.Button(row['title'], on_press=open_row, style=Pack(height=48, flex=1))
        if row_font is not None:
            from .appearance import list_button
            from .browser_ui import middle_filename
            opener.style.font_size = row_font
            middle_filename(list_button(opener))
        buttons.append(toga.Box(children=[opener,
            toga.Button('Remove', on_press=remove, style=Pack(height=48))],
            style=Pack(direction=ROW)))
    if row_font is not None:
        from .hub_controls import document_list
        container.add(document_list(buttons, 'No favourite files.'))
    elif buttons:
        container.add(*buttons)
    else:
        container.add(toga.Label('No favourite files.', style=Pack(margin_bottom=8)))
