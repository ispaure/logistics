"""Notebook documents in the shared mobile workspace, history and saved list."""
from pathlib import Path

from ..workspace import Repository
from .panel import NotebookPanel


def repository(app):
    return Repository(Path(app.private_root) / 'notebooks')


def panels(app):
    return app.__dict__.setdefault('_notebook_views', {})


async def open_notebook(app, *, path=None, resource=None, key=None, name=None, destination=None):
    if not app.active_host or not app.checkpoint():
        if resource is not None:
            resource.close()
        return False
    from ..notebook import Notebook, MAX_ARCHIVE
    from ..storage import NotebookDocument
    from services.documents.storage import DocumentResource
    from services.documents.mobile_storage import restore_notebook_resource, remember_notebook_resource
    generation = app.navigation_generation
    imports = None
    if path is not None:
        from commonUtils.runtime.resources.local import LocalFiles
        path = Path(path)
        resource = DocumentResource(LocalFiles(path.parent), path.name, max_bytes=MAX_ARCHIVE)
    if resource is not None:
        existing = next((panel for panel in panels(app).values()
            if panel.document is not None and panel.document.resource is not None
            and panel.document.resource.identity == resource.identity), None)
        if existing is not None:
            resource.close()
            existing.document.resource.check()
            if existing.web is None and existing.editor is not None:
                existing.mount_canvas()
            present(app, existing, destination=destination)
            return True
    session = next((s for s in app.workspace.sessions.values()
                    if s.identity == ('notebook', key)), None) if key else None
    panel = panels(app).get(session.id) if session else None
    if panel is not None:
        if resource is not None:
            resource.close()
        if panel.document and panel.document.resource:
            panel.document.resource.check()
        if panel.web is None:
            if panel.document is not None and panel.editor is not None:
                panel.mount_canvas()
            elif not await panel.load(lambda: panel.repository.open(key), key):
                return False
        present(app, panel, destination=destination)
        return True
    from mobile.workspace import MAX_SESSIONS
    if session is None and len(app.workspace.sessions) >= MAX_SESSIONS:
        if resource is not None:
            resource.close()
        raise ValueError('Close an open document before opening another (limit: 32).')
    panel = NotebookPanel(app, library=False)
    app.notebook_panel = panel
    try:
        binding = None
        recovery = repository(app) if resource is None or resource.policy.persistent else None
        if resource is None and key is not None:
            resource, binding = restore_notebook_resource(recovery, key)
        if resource is not None and resource.policy.persistent:
            from mobile.resource_imports import ResourceImports
            from features.rclone.mobile.storage_location import collection_path
            imports = ResourceImports(app.private_root, collection_root=collection_path(app.private_root))
            source_path = resource.provider.root / resource.path
            imported = imports.find(source_path)
            if key is None and imported is not None and imported['provider'] == 'notebook':
                key = imported['resource']
                previous, binding = restore_notebook_resource(recovery, key)
                if previous is not None:
                    previous.close()
        def load():
            active_resource = resource
            if resource is not None:
                try:
                    book = Notebook.read(resource.read())
                except (OSError, ValueError):
                    if recovery is None or key is None:
                        raise
                    book = recovery.open(key)
                    resource.close()
                    active_resource = None
                else:
                    if key is not None and recovery is not None:
                        recovered = recovery.open(key)
                        if binding and binding.get('dirty'):
                            book = recovered
                            if binding['revision'] != list(resource.revision):
                                resource.close()
                                active_resource = None
                        elif binding is None:
                            book = recovered
                        else:
                            book._recovery_revision = recovered._recovery_revision
                            recovery.save(key, book)
            else:
                book = recovery.open(key) if key else Notebook.new(name or 'Untitled notebook')
            document = NotebookDocument(book, resource=active_resource, recovery=recovery, key=key,
                                         changed=remember_notebook_resource)
            document.dirty = bool(binding and binding.get('dirty'))
            remember_notebook_resource(document)
            return document
        import asyncio
        document = await asyncio.to_thread(load)
        if app.navigation_generation != generation or not app.active_host:
            document.close()
            panel.dispose()
            return False
        panel.open_resource(document)
        if resource is not None and not resource.policy.persistent:
            panel.privacy_gate = getattr(getattr(app, 'cloud_client', None), 'session_privacy', None)
        if imports is not None:
            imports.remember(source_path, 'notebook', document.key)
    except Exception as error:
        if resource is not None:
            resource.close()
        panel.status.text = str(error)
        app.show_view(panel.view, destination=destination, route='notebook-error', title='Notebook')
        return False
    session = app.workspace.open('notebook', document.key, 'notebook', document.book.name,
                                 transient=not (resource is None or resource.policy.persistent))
    panel.session = session
    panel.view._reader_session_id = session.id
    panels(app)[session.id] = panel
    present(app, panel, destination=destination)
    return True


def present(app, panel, *, destination=None):
    session = panel.session
    app.notebook_panel = panel
    app.workspace.activate(session.id)
    if not session.transient:
        app.recent_documents.remember(session)
    app.show_view(panel.view, destination=destination, route='notebook:' + session.id,
                  title=panel.editor.notebook.name)
    app.save_workspace()
    app.refresh_document_list()


def close_notebook(app, key, choice, *, leaving_reader=False):
    panel = panels(app).get(key)
    if panel is not None and panel.busy:
        return False
    if panel is not None and panel.document is not None and panel.document.dirty:
        if choice == 'save':
            # Native handlers use the async save action before requesting close.
            return False
        if choice != 'discard' and panel.document.recovery is None:
            return False
    app.workspace.close(key, guard=lambda session: True)
    panels(app).pop(key, None)
    if panel is not None:
        panel.dispose()
    app.save_workspace()
    app.reader_closed(key)
    app.refresh_document_list()
    return True


async def retarget_notebook(app, panel, resource):
    """Adopt a verified Save As without rebuilding the canvas or its undo history."""
    import asyncio
    from ..notebook import Notebook
    from ..storage import NotebookDocument
    from services.documents.mobile_storage import remember_notebook_resource
    try:
        await asyncio.to_thread(lambda: Notebook.read(resource.read()))
        recovery = repository(app) if resource.policy.persistent else None
        document = NotebookDocument(panel.editor.notebook, resource=resource, recovery=recovery,
                                    changed=remember_notebook_resource)
        remember_notebook_resource(document)
    except Exception:
        resource.close()
        raise
    adopt_notebook_document(app, panel, document)
    present(app, panel)
    return True


def adopt_notebook_document(app, panel, document):
    resource = document.resource
    old = panel.document
    session = panel.session
    owners = getattr(app.workspace, 'window_owners', None)
    previous_identity = session.identity
    if owners is not None:
        owners.claim(app.workspace.window_id, ('notebook', document.key), private=not resource.policy.persistent)
        owners.release(app.workspace.window_id, previous_identity)
    panel.document, panel.key = document, document.key
    panel.editor.checkpoint = document.checkpoint
    session.resource, session.transient = document.key, not resource.policy.persistent
    session.history_source = None
    if not resource.policy.persistent:
        panel.privacy_gate = panel.privacy_gate or getattr(getattr(app, 'cloud_client', None), 'session_privacy', None)
    app.workspace.invalidate(session.id)
    if not resource.policy.persistent and (old is None or old.resource is None or old.resource.policy.persistent):
        panel.mount_canvas()
    if old is not None:
        old.close()


def retire_stale_notebooks(app):
    for key, panel in list(panels(app).items()):
        resource = panel.document.resource if panel.document else None
        if resource is None or resource.policy.persistent:
            continue
        try:
            resource.check()
        except (OSError, ValueError):
            # Unexpected revocation retires access and displayed content immediately.
            picker = getattr(app, '_editor_picker', None)
            if picker is not None and picker.binary_owner is panel:
                picker.clear()
            panel.session.title = ''
            panel.session.view.clear()
            panel.dispose()
            app.workspace.close(key, guard=lambda session: True)
            panels(app).pop(key, None)
            app.reader_closed(key)
    app.save_workspace()


def prepare_notebook_lock(app, *, discard=False):
    private = [panel for panel in panels(app).values()
               if panel.document is not None and panel.document.resource is not None
               and not panel.document.resource.policy.persistent]
    for panel in private:
        if panel.busy or (panel.document.dirty and not discard):
            present(app, panel)
            return False
    for panel in private:
        close_notebook(app, panel.session.id, 'discard')
    return True
