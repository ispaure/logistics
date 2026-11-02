"""Host routing and compatibility constructor for feature-owned Notes Libraries."""
import asyncio
from uuid import uuid4
from .preview import markdown_preview
from features.text_editor.notes import vault_root, local_library
from features.text_editor.mobile.notes_library import VaultBrowser as _VaultBrowser


class VaultBrowser(_VaultBrowser):
    def __init__(self, app, provider, root, destination):
        from .composition.presentation import notes_host
        super().__init__(notes_host(app), provider, root, destination)
        from .layout_participants import participants
        self._layout_subscription = participants(app).register('notes-library', self,
            lambda owner, frame: owner.reflow(frame.content_width(owner.destination, margin=0)), order=50)

    def dispose(self):
        subscription = getattr(self, '_layout_subscription', None)
        if subscription is not None:
            subscription.dispose()
        return super().dispose()


async def open_vault(app, provider, root, destination=None, *, title='', rows=None):
    if not local_library(provider):
        return None
    destination = destination or app.native_host.state.destination
    previous = getattr(app, 'vault_browser', None)
    if previous is not None and previous.valid() and not await previous.prepare_leave():
        return None
    if not app.checkpoint():
        return None
    owned = provider.reopen() if callable(getattr(provider, 'reopen', None)) else None
    if owned is not None:
        provider = owned
    previous = getattr(app, 'vault_browser', None)
    if previous is not None:
        previous.dispose()
    try:
        owner = VaultBrowser(app, provider, root, destination)
    except BaseException:
        if owned is not None:
            owned.close()
        raise
    owner.release_provider = owned.close if owned is not None else lambda: None
    owner.session = app.workspace.open('notes-library', uuid4().hex, 'markdown',
        'Notes Library' + (' — ' + title if title else ''), transient=True)
    app.vault_browser = owner
    if app.show_view(owner.view, destination=destination, route='notes-library:' + owner.session.id, title=owner.session.title) is False:
        owner.dispose()
        return None
    owner.sidebar.show_detail()
    await owner.load_folder(owner.root, rows=None if rows is None else owner.library.visible_rows(rows))
    return owner


async def offer_vault(app, browser, provider, root, rows):
    """Return True for Notes, False for files/no offer, or None for dismissal."""
    # Providers may be recreated on refresh; storage identity is stable.
    location = (str(provider.root), getattr(provider, 'remote', ''), root)
    pending = getattr(browser, '_notes_choice', None)
    if pending is not None and pending[0] == location:
        # Refresh/repeated taps must wait for the existing choice, rather than
        # treating a pending question as an already completed visit.
        return await asyncio.shield(pending[1])
    previous = getattr(browser, '_notes_location', None)
    browser._notes_location = location
    if previous == location or vault_root(provider, root, rows) is None:
        return False
    if not app.feature_enabled('text_editor') or app.routes.folders.restoring:
        return False
    origin = app.navigation_generation
    client = getattr(app, 'cloud_client', None)
    generation = getattr(client, 'generation', None)
    result = asyncio.get_running_loop().create_future()
    pending = browser._notes_choice = location, result
    try:
        opened = await _choose_vault(app, browser, provider, root, rows, location, origin, client, generation)
    except BaseException:
        if browser._notes_location == location:
            browser._notes_location = None
        result.cancel()
        raise
    else:
        result.set_result(opened)
        return opened
    finally:
        if getattr(browser, '_notes_choice', None) is pending:
            browser._notes_choice = None


async def _choose_vault(app, browser, provider, root, rows, location, origin, client, generation):
    from features.text_editor.mobile.document_dialogs import LibraryOpenDialog
    choice = await app.main_window.dialog(LibraryOpenDialog())
    if (not app.active_host or not app.feature_enabled('text_editor') or app.navigation_generation != origin
            or browser._notes_location != location
            or getattr(browser, '_notes_requested_location', location) != location):
        if browser._notes_location == location:
            browser._notes_location = None
        return False
    if getattr(provider, 'private', False) and (client is not app.cloud_client
            or generation != getattr(client, 'generation', None)):
        browser._notes_location = None
        return False
    if choice == 'files':
        return False
    if choice != 'notes':
        browser._notes_location = None
        return None
    opened = await open_vault(app, provider, root, destination='files', rows=rows) is not None
    if opened:
        # The file browser never entered this folder; a later entry is a new visit.
        browser._notes_location = None
    return opened
