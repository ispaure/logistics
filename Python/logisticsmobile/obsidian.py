"""Host routing and compatibility constructor for feature-owned Notes Libraries."""
from uuid import uuid4
from .preview import markdown_preview
from features.text_editor.notes import vault_root
from features.text_editor.mobile.notes_library import VaultBrowser as _VaultBrowser


class VaultBrowser(_VaultBrowser):
    def __init__(self, app, provider, root, destination):
        from .feature_hosts import notes_host
        super().__init__(notes_host(app), provider, root, destination)


async def open_vault(app, provider, root, destination=None, *, title='', rows=None):
    destination = destination or app.native_host.state.destination
    if not app.checkpoint():
        return None
    previous = getattr(app, 'vault_browser', None)
    if previous is not None:
        previous.dispose()
    owner = VaultBrowser(app, provider, root, destination)
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
