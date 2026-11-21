"""Cancellable, asynchronous Notes Library discovery for the Documents hub."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
from collections import deque
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Callable

import toga
from toga.style import Pack
from features.notes_library.notes import vault_root, operation
from commonUtils.runtime.operations import check_cancelled, OperationCancelled
from commonUtils.ui.native.forms import FittedLabel, fit_text
from commonUtils.ui.native.adaptive import allocated_width
from services.folders.labels import encrypted_copy_label
from .appearance import accessible_name, action_button, list_button, surface
from .control_icons import button_icons
from .browser_ui import middle_filename


def fit_discovery_status(label, frame):
    fit_text(label, allocated_width(label, frame.content_width('documents')))


def cancel(app):
    app._notes_discovery_token = None
    _cancel_scan_task(app)


def _cancel_scan_task(app):
    task = getattr(app, '_notes_discovery_task', None)
    if task is not None and not task.done():
        task.cancel()


def find_libraries(provider, *, cancelled=lambda: False):
    """Inspect root and two folder levels; never traverse a library's contents."""
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


@dataclass(frozen=True)
class _DiscoveryRequest:
    app: object
    token: object
    client: object
    generation: object

    def is_current(self):
        app = self.app
        return (app.active_host and app._notes_discovery_token is self.token
                and self.client is getattr(app, 'cloud_client', None)
                and self.generation == getattr(self.client, 'generation', None)
                and app.feature_enabled('notes_library'))

    def cancelled(self):
        return not self.is_current()


@dataclass(frozen=True)
class _DiscoveredLibrary:
    source_label: str
    root: str
    open_provider: Callable[[], object]


def _source_factories(app, client):
    roots = app.ordinary_file_roots(include_collections=False)
    factories = [(label, lambda label=label: app.storage_provider(label, roots)) for label in roots]
    if not app.feature_enabled('rclone'):
        return factories

    from features.rclone.localcrypt.mobile.resources import encrypted_storage
    for label, remote in app.existing_crypt_locations().items():
        factories.append((label, lambda remote=remote: encrypted_storage(app.private_root, client, remote, create=False)))

    from features.rclone.mobile.service import native_service
    for label, linked in app.linked_crypt_locations().items():
        location = linked.location
        # Retain the location for reopening and release the enumeration lease.
        linked.close()
        if label == encrypted_copy_label(f'{location.remote} · {location.remote}'):
            label = encrypted_copy_label(location.remote)
        factories.append((label, lambda location=location: native_service(client).localcrypt.open(location)))
    return factories


def _close_provider(provider):
    if provider is not None and hasattr(provider, 'close'):
        provider.close()


async def _acquire_provider(factory):
    """Retire a provider returned after its waiting row was cancelled."""
    worker = asyncio.create_task(asyncio.to_thread(factory))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        def retire(finished):
            if not finished.cancelled() and finished.exception() is None:
                _close_provider(finished.result())

        worker.add_done_callback(retire)
        raise


def _discover(request):
    app = request.app
    found, had_errors = [], False
    for label, factory in _source_factories(app, request.client):
        check_cancelled(request.cancelled)
        provider = None
        try:
            provider = factory()
            for root in find_libraries(provider, cancelled=request.cancelled):
                if app.folder_path_visible(root):
                    found.append(_DiscoveredLibrary(label, root, factory))
        except (OSError, ValueError):
            had_errors = True
        finally:
            _close_provider(provider)
    return found, had_errors


async def _open_library(request, library, status):
    if not request.is_current():
        return
    provider = None
    try:
        provider = await _acquire_provider(library.open_provider)
        if not request.is_current():
            return
        from .obsidian import open_vault
        await open_vault(request.app, provider, library.root, 'documents')
    except (OSError, ValueError) as error:
        status.text = str(error)[:160]
    finally:
        _close_provider(provider)


def _library_button(request, library, status, row_font):
    from services.documents.mobile_locations import COPIES, enabled
    from .local_sources import device_files_label

    async def open_library(widget=None, **kwargs):
        await _open_library(request, library, status)

    app = request.app
    label, root = library.source_label, library.root
    location = label.removesuffix(' - Encrypted Copy')
    encrypted = location != label
    if enabled(app.private_root):
        location = {'Local files': COPIES, 'Shared files': device_files_label(app)}.get(location, location)
    path = PurePosixPath(root)
    caption = path.name or location
    button = toga.Button(caption, on_press=open_library, style=Pack(height=48))
    if row_font is not None:
        button.style.font_size = row_font
    list_button(button)
    surface(button, radius=0, background='transparent', outlined=False, eink_outlined=False)
    kinds = [('storage_local', 'On-device library')]
    if encrypted:
        kinds.append(('storage_unlocked', 'Encrypted library, unlocked'))
    button_icons(button, kinds)
    middle_filename(button)
    # Keep the full source and logical path for same-named libraries.
    source_label = label if encrypted else location
    source = f'{source_label} / {path.parent}' if path.parent.parts else source_label
    accessible_name(button, f'{caption} · {source}' if root else source)
    return button


def _show_libraries(request, rows, status, row_font, libraries, had_errors):
    for library in libraries:
        rows.add(_library_button(request, library, status, row_font))
    if rows.children:
        surface(rows, radius=16)
    else:
        from .hub_controls import empty_document_row
        rows.add(empty_document_row('No Notes libraries found.'))
    status.text = 'Some locations could not be checked.' if had_errors else ''


async def _run_discovery(request, rows, status, row_font):
    try:
        libraries, had_errors = await asyncio.to_thread(_discover, request)
        if request.is_current():
            _show_libraries(request, rows, status, row_font, libraries, had_errors)
    except (asyncio.CancelledError, OperationCancelled):
        return


def _fit_status_label(app, key, label):
    from .layout_participants import participants, LayoutFrame
    label._layout_subscription = participants(app).register(key, label, fit_discovery_status)
    fit_discovery_status(label, LayoutFrame(app.main_window.size.width, app.adaptive.content_width))


def populate(app, container, *, title='Notes Library', refresh=True, title_style=None, row_font=None):
    container.clear()
    container.add(toga.Label(title, style=title_style or
                             Pack(font_size=19, font_weight='bold', margin_top=16, margin_bottom=8)))
    if not app.feature_enabled('notes_library'):
        container.add(toga.Label('Notes Library is disabled.'))
        return
    rows = toga.Box(style=Pack(direction='column'))
    status = FittedLabel('Looking for libraries…', style=Pack(font_size=12))
    container.add(rows, status)
    _fit_status_label(app, 'notes-discovery-status', status)
    if app.home_unlock_candidates():
        unlock_hint = FittedLabel('Unlock encrypted copies to include their libraries.', style=Pack(font_size=12))
        container.insert(0, unlock_hint)
        _fit_status_label(app, 'notes-discovery-unlock', unlock_hint)

    token = app._notes_discovery_token = object()
    _cancel_scan_task(app)
    client = getattr(app, 'cloud_client', None)
    request = _DiscoveryRequest(app, token, client, getattr(client, 'generation', None))
    app._notes_discovery_task = app.loop.create_task(_run_discovery(request, rows, status, row_font))

    async def create(widget=None, **kwargs):
        if request.is_current():
            await app.editor_picker().show_editor_browser('folder')

    container.add(action_button(toga.Button('New Notes Library…', on_press=create, style=Pack(height=48))))
    if refresh:
        container.add(toga.Button('Refresh libraries',
            on_press=lambda widget: populate(app, container, title=title,
                title_style=title_style.copy() if title_style is not None else None, row_font=row_font),
            style=Pack(height=48)))
