"""Cancellable, asynchronous Notes Library discovery for the Documents hub."""
import asyncio
from pathlib import PurePosixPath
import toga
from toga.style import Pack
from features.notes_library.notes import vault_root, operation
from commonUtils.runtime.operations import check_cancelled, OperationCancelled
from commonUtils.ui.native.forms import FittedLabel, fit_text
from commonUtils.ui.native.adaptive import allocated_width
from .appearance import accessible_name, list_button, surface
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
    """Inspect root and two folder levels; never traverse a library's contents."""
    from collections import deque
    pending, found, seen = deque([('', 0)]), [], set()
    with operation(provider, cancelled):
        while pending:
            check_cancelled(cancelled)
            folder, depth = pending.popleft()
            if folder in seen:
                continue
            seen.add(folder)
            rows = provider.list(folder, cancelled=cancelled)
            if vault_root(provider, folder, rows) is not None:
                found.append(folder)
                # A library owns its subtree; nested notebooks aren't libraries.
                continue
            if depth < 2:
                pending.extend((row['path'], depth + 1) for row in rows
                               if row['directory'] and not row['name'].startswith('.'))
    return found


def populate(app, container, *, title='Notes Library', refresh=True):
    container.clear()
    container.add(toga.Label(title, style=Pack(font_size=19, font_weight='bold', margin_top=16, margin_bottom=8)))
    if not app.feature_enabled('notes_library'):
        container.add(toga.Label('Notes Library is disabled.'))
        return
    rows = toga.Box(style=Pack(direction='column'))
    status = FittedLabel('Looking for libraries…', style=Pack(font_size=12))
    container.add(rows, status)
    from .layout_participants import participants, LayoutFrame
    layout = participants(app)
    def fit_label(key, label):
        label._layout_subscription = layout.register(key, label, fit_discovery_status)
        fit_discovery_status(label, LayoutFrame(app.main_window.size.width, app.adaptive.content_width))

    fit_label('notes-discovery-status', status)
    if app.home_unlock_candidates():
        unlock_hint = FittedLabel('Unlock encrypted copies to include their libraries.', style=Pack(font_size=12))
        container.insert(0, unlock_hint)
        fit_label('notes-discovery-unlock', unlock_hint)
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
        roots = app.ordinary_file_roots(include_collections=False)
        factories = [(label, lambda label=label: app.storage_provider(label, roots)) for label in roots]
        if app.feature_enabled('rclone'):
            from features.rclone.localcrypt.mobile.resources import encrypted_storage
            for label, remote in app.existing_crypt_locations().items():
                factories.append((label, lambda remote=remote: encrypted_storage(app.private_root, client, remote, create=False)))
            from features.rclone.mobile.service import native_service
            for label, linked in app.linked_crypt_locations().items():
                location = linked.location
                linked.close()
                # A copy named after its remote needs only one name in the hub.
                remote_label = location.remote + ' - Encrypted Copy'
                if label == f'{location.remote} · {location.remote} - Encrypted Copy':
                    label = remote_label
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
                encrypted = label.endswith(' - Encrypted Copy')
                location = label.removesuffix(' - Encrypted Copy')
                caption = PurePosixPath(root).name or location
                button = toga.Button(caption, on_press=open_library, style=Pack(height=48))
                list_button(button)
                surface(button, radius=0, background='transparent', outlined=False, eink_outlined=False)
                kinds = [('storage_local', 'On-device library')]
                if encrypted:
                    kinds.append(('storage_unlocked', 'Encrypted library, unlocked'))
                button_icons(button, kinds)
                middle_filename(button)
                # Keep the full source and logical path for same-named libraries.
                parent = PurePosixPath(root).parent
                source = f'{label} / {parent}' if parent.parts else label
                accessible_name(button, f'{caption} · {source}' if root else source)
                rows.add(button)
            if rows.children:
                surface(rows, radius=16)
            else:
                from .hub_controls import empty_document_row
                rows.add(empty_document_row('No Notes libraries found.'))
            status.text = 'Some locations could not be checked.' if errors else ''
        except (asyncio.CancelledError, OperationCancelled):
            return
    app._notes_discovery_task = app.loop.create_task(scan())
    if refresh:
        container.add(toga.Button('Refresh libraries', on_press=lambda widget: populate(app, container), style=Pack(height=48)))
