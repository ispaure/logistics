"""Host routing and compatibility constructor for feature-owned Notes Libraries."""
from uuid import uuid4
from .preview import markdown_preview
from features.text_editor.notes import vault_root
from features.text_editor.mobile.notes_library import VaultBrowser as _VaultBrowser


class VaultBrowser(_VaultBrowser):
    def __init__(self, app, provider, root, destination):
        from .composition.presentation import notes_host
        super().__init__(notes_host(app), provider, root, destination)


async def open_vault(app, provider, root, destination=None, *, title='', rows=None):
    destination = destination or app.native_host.state.destination
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
    if rows is None:
        await owner.load_folder(owner.root)
    else:
        owner.folders[owner.root] = owner.library.visible_rows(rows)
        owner.render_tree()
    return owner


async def offer_vault(app, browser, provider, root, rows):
    """Ask once per entered location, using its existing immediate listing."""
    from features.text_editor.mobile.document_dialogs import LibraryOpenDialog
    # Providers may be recreated on refresh; storage identity is stable.
    location = (str(provider.root), getattr(provider, 'remote', ''), root)
    previous = getattr(browser, '_notes_location', None)
    browser._notes_location = location
    if previous == location or vault_root(provider, root, rows) is None:
        return False
    if not app.feature_enabled('text_editor') or app.routes.folders.restoring:
        return False
    origin = app.navigation_generation
    client = getattr(app, 'cloud_client', None)
    generation = getattr(client, 'generation', None)
    choice = await app.main_window.dialog(LibraryOpenDialog())
    if (choice != 'notes' or not app.active_host or app.navigation_generation != origin
            or browser._notes_location != location):
        return False
    if getattr(provider, 'private', False) and (client is not app.cloud_client
            or generation != getattr(client, 'generation', None)):
        return False
    return await open_vault(app, provider, root, rows=rows) is not None
