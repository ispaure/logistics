"""File-scoped menu commands, independent of the active editor."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import toga

from commonUtils.runtime.resources.local import LocalFiles
from services.documents.storage import FileItem, document_display_name
from . import favourites, outbound_share
from .document_sources import local_document_path, local_reference_available, saved_connection


def reference_available(app, source):
    if not source:
        return False
    kind = source.get('type')
    if kind == 'local':
        return local_reference_available(app, source)
    if kind not in {'remote', 'crypt', 'download'}:
        return False
    client = getattr(app, 'cloud_client', None)
    try:
        remote = client.resolve_remote(source['remote'], source['identity'], cipher=kind != 'remote')
    except (AttributeError, OSError, ValueError):
        return False
    field = 'identities' if kind == 'remote' else 'crypt_identities'
    return any(record.get(field, {}).get(remote) == source['identity']
               for record in client.package_records)


def row_actions(app, provider, row, *, anchor=None, opener=None):
    if provider is None or not row or row.get('directory') or not row.get('path'):
        return []
    item = FileItem(provider, row['path'], row.get('revision'))
    actions = []
    try:
        source, cipher = favourites.resource_reference(app, provider, item.path)
        title = document_display_name(provider, item.path)
        actions.append(favourites.favourite_action(
            app, source, title, opener or dict(kind='file'), cipher, validate=item.validate))
    except (OSError, ValueError):
        pass
    if outbound_share.supported():
        actions.append((outbound_share.SEND, partial(outbound_share.send, app, item, anchor=anchor)))
    return actions


def _resolve_reference(app, source):
    kind = source['type']
    if kind == 'local':
        path = local_document_path(app, source['path'])
        return FileItem(LocalFiles(path.parent), path.name), lambda: None
    from features.rclone.mobile.service import native_service
    from features.rclone.remote_access import NativeRemoteLocation
    from features.rclone.localcrypt.mobile.locations import LocalCryptLocation, OfflineCryptLocation
    from services.documents.locations import collection_path

    client = getattr(app, 'cloud_client', None)
    if client is None:
        raise PermissionError('Unlock the file’s connection and try again.')
    identity = source['identity']
    remote = client.resolve_remote(source['remote'], identity, cipher=kind != 'remote')
    service = native_service(client)
    path = source['key']
    if kind == 'remote':
        provider = service.remotes.open(NativeRemoteLocation(remote, identity=identity))
    elif kind == 'crypt':
        provider = service.localcrypt.open(LocalCryptLocation(collection_path(app.private_root, True), remote,
            namespace=source['namespace'], storage_root=app.private_root, create=False, cipher_identity=identity))
    elif kind == 'download':
        copies = getattr(app, 'crypt_copies', None)
        if copies is None:
            raise PermissionError('Unlock the downloaded file’s connection and try again.')
        if copies.record(path)['identity'] != identity:
            raise ValueError('The downloaded file connection changed.')
        provider = service.localcrypt.open(OfflineCryptLocation(copies, path))
        path = provider.name
    else:
        raise ValueError('This file no longer has an opening reference.')
    return FileItem(provider, path), provider.close


def reference_actions(app, source, title, opener, *, anchor=None, favourite=True):
    if not source or source['type'] not in {'local', 'remote', 'crypt', 'download'}:
        return []
    resolve = partial(_resolve_reference, app, source)
    actions = []

    def validate():
        item, close = resolve()
        try:
            item.validate()
        finally:
            close()

    if favourite:
        try:
            cipher = None
            if source['type'] != 'local' and not saved_connection(app, source['remote'], source['identity']):
                cipher = favourites.MobileCredentialCipher(SimpleNamespace(client=app.cloud_client,
                    remote=source['remote'], identity=source['identity']), app)
            actions.append(favourites.favourite_action(app, source, title, opener, cipher, validate=validate))
        except (OSError, ValueError):
            pass

    if outbound_share.supported():
        async def send():
            try:
                item, close = await asyncio.to_thread(resolve)
            except (OSError, ValueError) as error:
                if app.active_host:
                    await app.main_window.dialog(toga.InfoDialog(outbound_share.SEND, str(error)))
                return False
            try:
                return await outbound_share.send(app, item, anchor=anchor)
            finally:
                close()
        actions.append((outbound_share.SEND, send))
    return actions


def native_menu(app, button, actions):
    import inspect
    from .action_menu import WorkspaceMenu

    def invoke(callback):
        if app.active_host:
            result = callback()
            if inspect.isawaitable(result):
                app.loop.create_task(result)

    button.document_actions = WorkspaceMenu(button, actions, invoke=invoke,
        context=lambda: app._impl.native, fallback=lambda: app.show_editor_actions(None, menu=button.document_actions))
    return button
