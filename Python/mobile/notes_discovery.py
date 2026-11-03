"""Bounded, asynchronous Notes Library discovery for the Documents hub."""
import asyncio
from pathlib import PurePosixPath
import toga
from toga.style import Pack
from features.notes_library.notes import vault_root, operation
from commonUtils.runtime.operations import check_cancelled, OperationCancelled
from commonUtils.ui.native.forms import FittedLabel, fit_text
from commonUtils.ui.native.adaptive import allocated_width
from .control_icons import button_icons
from .browser_ui import middle_filename


def fit_discovery_status(label, frame):
    fit_text(label, allocated_width(label, frame.content_width('documents')))


def cancel(app):
    app._notes_discovery_token = None
    task = getattr(app, '_notes_discovery_task', None)
    if task is not None and not task.done():
        task.cancel()


def find_libraries(provider, *, cancelled=lambda: False):
    pending, found, count, folders = [('', 0)], [], 0, 0
    with operation(provider, cancelled):
        while pending:
            check_cancelled(cancelled)
            folder, depth = pending.pop(0)
            folders += 1
            if folders > 200:
                raise ValueError('Library discovery reached its 200-folder limit.')
            rows = provider.list(folder, cancelled=cancelled)
            count += len(rows)
            if count > 10000:
                raise ValueError('Library discovery reached its 10,000-entry limit.')
            if vault_root(provider, folder, rows) is not None:
                found.append(folder)
            if depth < 2:
                pending.extend((row['path'], depth + 1) for row in rows
                               if row['directory'] and not row['name'].startswith('.'))
                if len(pending) > 200:
                    raise ValueError('Library discovery reached its 200-folder limit.')
    return found


def populate(app, container):
    if not app.feature_enabled('notes_library'):
        return
    container.clear()
    container.add(toga.Label('Notes Library', style=Pack(font_size=20, font_weight='bold', margin_top=12)))
    rows = toga.Box(style=Pack(direction='column'))
    status = FittedLabel('Looking for libraries…', style=Pack(font_size=12))
    container.add(rows, status)
    from .layout_participants import participants, LayoutFrame
    status._layout_subscription = participants(app).register(
        'notes-discovery-status', status, fit_discovery_status)
    fit_discovery_status(status, LayoutFrame(app.main_window.size.width, app.adaptive.content_width))
    token = object()
    app._notes_discovery_token = token
    previous = getattr(app, '_notes_discovery_task', None)
    if previous is not None and not previous.done():
        previous.cancel()
    client = getattr(app, 'cloud_client', None)
    generation = getattr(client, 'generation', None)
    def valid():
        return (app.active_host and app._notes_discovery_token is token
                and client is getattr(app, 'cloud_client', None)
                and generation == getattr(client, 'generation', None)
                and app.feature_enabled('notes_library'))
    def discover():
        from commonUtils.runtime.resources.local import LocalFiles
        from services.documents.locations import collection_path
        from features.rclone.localcrypt.mobile.resources import encrypted_storage
        factories = []
        local = collection_path(app.private_root)
        if local.is_dir():
            factories.append(('Local', lambda: LocalFiles(local)))
        if app.feature_enabled('rclone'):
            for label, remote in app.existing_crypt_locations().items():
                factories.append((label, lambda remote=remote: encrypted_storage(app.private_root, client, remote, create=False)))
            from features.rclone.mobile.service import native_service
            for label, linked in app.linked_crypt_locations().items():
                location = linked.location
                linked.close()
                factories.append((label, lambda location=location: native_service(client).localcrypt.open(location)))
        found, errors = [], []
        for label, factory in factories:
            check_cancelled(lambda: not valid())
            provider = None
            try:
                provider = factory()
                for root in find_libraries(provider, cancelled=lambda: not valid()):
                    if app.folder_path_visible(root):
                        found.append((label, root, factory))
            except (OSError, ValueError) as error:
                errors.append(str(error))
            finally:
                if provider is not None and hasattr(provider, 'close'):
                    provider.close()
        return found, errors
    async def scan():
        try:
            found, errors = await asyncio.to_thread(discover)
            if not valid():
                return
            for label, root, factory in found:
                async def open_library(widget=None, root=root, factory=factory, **kwargs):
                    if not valid():
                        return
                    provider = None
                    try:
                        provider = await asyncio.to_thread(factory)
                        if not valid():
                            return
                        from .obsidian import open_vault
                        await open_vault(app, provider, root, 'documents')
                    except (OSError, ValueError) as error:
                        status.text = str(error)[:160]
                    finally:
                        if provider is not None and hasattr(provider, 'close'):
                            provider.close()
                encrypted = label.startswith('LocalCrypt: ')
                location = label.removeprefix('LocalCrypt: ')
                caption = PurePosixPath(root).name or location
                if root and encrypted:
                    caption += ' · ' + location
                button = toga.Button(caption, on_press=open_library, style=Pack(height=48))
                kinds = [('storage_local', 'On-device library')]
                if encrypted:
                    kinds.append(('storage_unlocked', 'Encrypted library, unlocked'))
                button_icons(button, kinds)
                middle_filename(button)
                rows.add(button)
            status.text = ('Some locations could not be checked.' if errors else '' if found
                           else 'No libraries found within two folders. Unlock LocalCrypt credentials to include encrypted libraries.')
        except (asyncio.CancelledError, OperationCancelled):
            return
    app._notes_discovery_task = app.loop.create_task(scan())
    container.add(toga.Button('Refresh libraries', on_press=lambda widget: populate(app, container), style=Pack(height=48)))
