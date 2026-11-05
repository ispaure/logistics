"""Notebook documents in the shared mobile workspace, history and saved list."""
from pathlib import Path

from features.notebooks.recovery import Repository
from features.notebooks.mobile.panel import NotebookPanel


def repository(app):
    return Repository(Path(app.private_root) / 'notebooks')


def panels(app):
    return app.__dict__.setdefault('_notebook_views', {})


async def open_notebook(app, *, path=None, resource=None, key=None, name=None, destination=None):
    if not app.require_feature('notebooks'):
        if resource is not None:
            resource.close()
        return False
    if not app.active_host or not app.checkpoint():
        if resource is not None:
            resource.close()
        return False
    from features.notebooks.notebook import Notebook, MAX_ARCHIVE
    from features.notebooks.storage import NotebookDocument
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
        if panel.web is None and panel.editor is None:
            if not await panel.load(lambda: panel.repository.open(key), key, mount=False):
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
            from services.documents.locations import collection_path
            imports = ResourceImports(app.private_root, collection_root=collection_path(app.private_root))
            source_path = resource.provider.root / resource.path
            imported = imports.find(source_path)
            if key is None and imported is not None and imported['provider'] == 'notebook':
                key = imported['resource']
                # Import identities are resolved after the initial key lookup.
                # Reuse the live owner rather than replacing its RAM draft/undo.
                existing = next((owner for owner in panels(app).values()
                                 if owner.key == key and not owner.closed), None)
                if existing is not None:
                    resource.close()
                    panel.dispose()
                    present(app, existing, destination=destination)
                    return True
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
                            recovery.adopt(key, book, recovered)
                            recovery.save(key, book)
            else:
                book = recovery.open(key) if key else Notebook.new(name or 'Untitled notebook')
            document = NotebookDocument(book, resource=active_resource, recovery=recovery, key=key,
                                         changed=remember_notebook_resource)
            document.dirty = bool(binding and binding.get('dirty'))
            document.source_unavailable = bool(binding and active_resource is None)
            remember_notebook_resource(document)
            return document
        import asyncio
        document = await asyncio.to_thread(load)
        if app.navigation_generation != generation or not app.active_host:
            document.close()
            panel.dispose()
            return False
        panel.open_resource(document, mount=False)
        if resource is not None and not resource.policy.persistent:
            panel.privacy_gate = getattr(resource.provider, 'privacy_gate', None)
            from mobile.protection import for_app
            for_app(app).changed()
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
    from mobile.document_location import install_document_location
    install_document_location(panel.view, copies=panel.document.resource if panel.document is not None else None)
    panel.view._native_reader_title = lambda: panel.editor.notebook.name if panel.editor is not None else ''
    panel.view._document_path = lambda: notebook_location(panel)
    app.show_view(panel.view, destination=destination, route='notebook:' + session.id,
                  title=panel.editor.notebook.name)
    if panel.web is None:
        panel.mount_canvas()
    app.save_workspace()
    app.refresh_document_list()


def notebook_location(panel):
    from .storage import display_path
    if panel.editor is None or panel.closed:
        return None
    document = panel.document
    if document is not None and document.resource is not None:
        return display_path(document.resource.provider, document.resource.path)
    name = panel.editor.notebook.name
    if document is not None and document.recovery is not None and document.key:
        return f'{name}\n\n{document.recovery.root / document.key}'
    if document is None and panel.key:
        return f'{name}\n\n{panel.repository.root / panel.key}'
    return name


def close_notebook(app, key, choice, *, leaving_reader=False):
    panel = panels(app).get(key)
    if panel is not None and (panel.busy or (choice != 'discard' and getattr(panel, 'native_input_pending', False))):
        return False
    if panel is not None and panel.document is not None and panel.document.dirty:
        if choice == 'save':
            # Native handlers use the async save action before requesting close.
            return False
        if choice != 'discard' and panel.document.recovery is None:
            return False
        if choice == 'discard':
            try:
                panel.document.discard()
            except (OSError, ValueError, KeyError) as error:
                show_notebook_close_error(app, panel, error)
                return False
    if panel is not None and panel.document is not None and panel.document.recovery_deleted and panel.document.resource is None:
        try:
            from mobile.resource_imports import ResourceImports
            from services.documents.locations import collection_path
            app.recent_documents.forget('notebook', panel.key)
            ResourceImports(app.private_root, collection_root=collection_path(app.private_root)).forget('notebook', panel.key)
        except (OSError, ValueError, KeyError) as error:
            show_notebook_close_error(app, panel, error)
            return False
    app.workspace.close(key, guard=lambda session: True)
    panels(app).pop(key, None)
    if panel is not None:
        panel.dispose()
    app.save_workspace()
    app.reader_closed(key)
    app.refresh_document_list()
    return True


def show_notebook_close_error(app, panel, error):
    """A native close prompt must not leave failures in a detached status label."""
    import toga
    message = 'Could not close the notebook. Your draft is retained. ' + str(error)
    panel.status.text = message
    async def explain():
        await app.main_window.dialog(toga.ErrorDialog('Notebook could not close', message))
    app.loop.create_task(explain())


async def retarget_notebook(app, panel, resource):
    """Adopt a verified Save As without rebuilding the canvas or its undo history."""
    import asyncio
    from features.notebooks.notebook import Notebook
    from features.notebooks.storage import NotebookDocument
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
    if panel.web is not None:
        from features.notebooks.protocol import update_script
        await panel.web.evaluate_javascript(update_script(panel.state()))
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
        panel.privacy_gate = panel.privacy_gate or getattr(resource.provider, 'privacy_gate', None)
        from mobile.protection import for_app
        for_app(app).changed()
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
        if panel.busy or ((panel.document.dirty or getattr(panel, 'native_input_pending', False)) and not discard):
            present(app, panel)
            return False
    for panel in private:
        close_notebook(app, panel.session.id, 'discard')
    return True


def install_notebook_controls(panel):
    """Native reader chrome is host composition, independent of the canvas."""
    if not type(panel.view._impl).__module__.startswith('toga_iOS.'):
        return
    import toga
    from mobile.control_icons import icon_button
    import json
    from mobile.action_menu import FeatureCommands

    def action(name):
        async def invoke(widget=None, **kwargs):
            if panel.closed or not panel.app.active_host:
                return
            if name == 'library' and hasattr(panel, 'session'):
                # Native Close must remain usable when the WebView cannot answer.
                # The session owner flushes boundedly and presents Save/Discard/Cancel.
                panel.app.__dict__.setdefault('_reader_returns', {})[panel.session.id] = ('home', None, False)
                panel.app.request_reader_close(panel.session.id)
                return
            if panel.web is None:
                return
            await panel.web.evaluate_javascript('window.notebookNativeAction?.(' + json.dumps(name) + ')')
        return invoke

    close = action('library')
    panel.view._reader_close_button = icon_button('close', 'Close document', on_press=close)
    buttons = [icon_button(icon, label, on_press=action(name)) for icon, label, name in (
        ('contents', 'Pages Overview', 'pages'),
        ('notes_links', 'Page template and layers', 'layers'),
        ('appearance', 'View and input', 'view'),
    )]
    more = icon_button('more', 'Notebook actions')
    panel.native_actions = FeatureCommands(more, panel.app, [
        (label, action(name)) for label, name in (
            ('Pages Overview', 'pages'), ('Page template and layers', 'layers'),
            ('View and input…', 'view'), ('Save', 'save'), ('Save As…', 'save-as'),
            ('Export .rmdoc', 'export'), ('Show in folder', 'show-in-folder'),
            ('Document location', 'document-location'), ('Hide tools', 'hide-tools'),
            ('Add page', 'add-page'), ('Close document', 'library'),
            ('Delete document…', 'delete-file'),
        )], action('document'))
    buttons.append(more)
    panel.view._native_reader_toolbar = toga.Box(children=buttons)
    panel.view._native_reader_buttons = lambda: buttons


async def show_notebook_in_folder(panel):
    from mobile.document_sources import show_in_folder
    if not panel.closed and panel.app.active_host:
        return await show_in_folder(panel.app, panel.session, panel)
    return False


async def delete_notebook(panel):
    """Confirm and retire one document through its storage/recovery owners."""
    import asyncio
    from services.documents.authoring.document_dialogs import DocumentDialog
    from mobile.resource_imports import ResourceImports
    app, document, session = panel.app, panel.document, panel.session
    if panel.closed or not app.active_host or getattr(panel, '_delete_pending', False):
        return False
    if document is None or (not document.writable and not document.deletion_started):
        raise ValueError('This notebook cannot be deleted.')
    resource = document.resource
    binding = (resource.path, resource.revision) if resource is not None else None
    session_resource = session.resource
    def current():
        return (not panel.closed and app.active_host and panel.document is document
                and panel.session is session and session.resource == session_resource
                and document.resource is resource
                and (resource is None or (resource.path, resource.revision) == binding))
    def single_window():
        if len(app.scene_manager.owners.hosts) > 1:
            raise ValueError('Close other app windows before deleting a document.')
    single_window()
    warning = ('Permanently delete this notebook and its recovery draft? '
               'Unsaved changes will also be removed.')
    if document.deletion_started:
        warning = 'Notebook data was already deleted in part or in full. Retry the remaining cleanup?'
    elif resource is not None:
        warning += ' The file will be deleted from its folder.'
    canvas = getattr(panel, 'bridge', None)
    was_busy, panel.busy = panel.busy, True
    panel._delete_pending = True
    try:
        choice = await app.main_window.dialog(DocumentDialog(
            'Delete ' + document.book.name + '?', warning, delete=True))
        if choice != 'delete' or not current():
            return False
        single_window()
        worker = asyncio.create_task(asyncio.to_thread(document.delete))
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            # A thread cannot be cancelled. Keep ownership until it settles so
            # a new canvas command or lock cannot overlap destructive work.
            while not worker.done():
                try:
                    await asyncio.shield(worker)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if not worker.cancelled():
                worker.exception()  # observe a failure without hiding cancellation
            raise
        if not current():
            return False
        app.recent_documents.forget('notebook', session_resource)
        imports = getattr(app, 'resource_imports', None) or ResourceImports(app.private_root)
        imports.forget('notebook', session_resource)
        panel.busy = False
        returns = app.__dict__.setdefault('_reader_returns', {})
        closing = app.__dict__.setdefault('_reader_closing', set())
        had_return, previous_return = session.id in returns, returns.get(session.id)
        was_closing = session.id in closing
        returns[session.id] = ('home', None, False)
        closing.add(session.id)
        try:
            try:
                closed = app.close_session(session.id, choice='discard')
            except Exception as error:
                raise OSError('Notebook data was deleted, but session cleanup failed. Retry Delete or use Save As.') from error
            if not closed:
                raise OSError('Notebook data was deleted, but the editor could not close. Retry Delete or use Save As.')
            return True
        finally:
            if session.id in app.workspace.sessions:
                if had_return:
                    returns[session.id] = previous_return
                else:
                    returns.pop(session.id, None)
                if not was_closing:
                    closing.discard(session.id)
    finally:
        panel._delete_pending = False
        if panel.closed:
            panel.busy = False
        elif getattr(panel, 'bridge', None) is canvas:
            panel.busy = was_busy


async def notes_editor(app, library, path):
    """Embed the regular notebook canvas in a library, with no extra reader route."""
    import asyncio
    if not app.require_feature('notebooks'):
        raise ValueError('Enable Notebooks to edit Remarkable Documents.')
    from features.notebooks.notebook import Notebook, MAX_ARCHIVE
    from features.notebooks.storage import NotebookDocument
    from .storage import DocumentResource

    class LibraryPanel(NotebookPanel):
        def state(self):
            state = super().state()
            state.update(native_close=True, notes_library=True, has_source=False, can_delete=False)
            return state

        async def perform(self, action, **options):
            if action.get('op') in ('library', 'save-as', 'transfer', 'show-in-folder', 'delete-file'):
                if self.web is not None:
                    from features.notebooks.protocol import update_script
                    await self.web.evaluate_javascript(update_script(self.state()))
                return
            return await super().perform(action, **options)

    class Embedded:
        owns_document_swipes = True

        def __init__(self, panel):
            self.panel, self.view = panel, panel.view
        @property
        def dirty(self):
            return self.panel.document.dirty or self.panel.native_input_pending
        @property
        def busy(self):
            return self.panel.busy
        async def flush(self):
            if getattr(self.panel, 'native_transport', False):
                await self.panel.flush_input()
                return
            from commonUtils.ui.native.text_size import native_backend
            if self.panel.web is not None and native_backend(self.panel.web).startswith(('toga_iOS.', 'toga_android.')):
                for _ in range(100):
                    if await self.panel.web.evaluate_javascript('window.notebookIdle?.() === true'):
                        return
                    if self.panel.closed or not library.valid():
                        raise ValueError('Notes Library closed.')
                    await asyncio.sleep(.02)
                raise ValueError('Finish the current stroke and try again.')
        async def save(self):
            if getattr(self.panel, 'native_transport', False):
                return await self.panel.save_from_view()
            await self.flush()
            await self.panel.perform({'op': 'save'})
            return not self.dirty
        def dispose(self):
            self.panel.dispose()

    resource = DocumentResource(library.provider, path, max_bytes=MAX_ARCHIVE)
    panel = LibraryPanel(app, library=False)
    epoch = library.epoch
    try:
        book = await asyncio.to_thread(lambda: Notebook.read(resource.read(
            cancelled=lambda: not library.valid() or library.epoch != epoch)))
        if not library.valid() or library.epoch != epoch:
            raise ValueError('Notes Library closed.')
        document = NotebookDocument(book, resource=resource, changed=lambda doc: setattr(library.session, 'dirty', doc.dirty)
                                    if library.session is not None else None)
        if not resource.policy.persistent:
            panel.privacy_gate = getattr(resource.provider, 'privacy_gate', None)
            from mobile.protection import for_app
            for_app(app).changed()
        panel.open_resource(document)
        return Embedded(panel)
    except BaseException:
        panel.dispose()
        resource.close()
        raise
