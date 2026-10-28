"""Library-session controllers retain identity while inactive decoders suspend."""
from .composition.assembly import composed_workflow
from features.books.mobile.reader_controller import EpubController
from features.comics.mobile.reader_controller import ComicController

from .reader_ui import ReaderUI
from .reader_host import ReaderHost


@composed_workflow('epub_controller', EpubController)
@composed_workflow('comic_controller', ComicController)
class ReaderController(ReaderHost, ReaderUI):
    def __init__(self, manager, session=None):
        self.manager, self.app, self.session = manager, manager.app, session
        from .composition.presentation import reading_presentation
        self.format_services = reading_presentation(self)
        from .composition.presentation import library_host
        self.library_host = library_host(self.app)
        self.presentation_destination = self.app.native_host.state.destination

    def show_view(self, view, **kwargs):
        self.refresh_folder_action()
        self.manager.bind(self)
        route = 'reader:' + self.session.id if self.session is not None else 'library'
        suffix = kwargs.pop('reader_route', None)
        kwargs.update(destination=self.presentation_destination,
                      route=route + (':' + suffix if suffix else ''),
                      title=kwargs.get('title') or (self.session.title if self.session else 'Books & Comics'))
        return self.app.show_view(view, **kwargs)

    def set_book_busy(self, busy):
        super().set_book_busy(busy)
        self.manager.update_session(self)

    async def open_book(self, key, *, password=None):
        if self.session is None or key != self.session.resource:
            return await self.manager.open(key, password=password)
        if self.book_reader is not None and password is None:
            self.show_library()
            if self.book_record['kind'] == 'epub':
                # An existing decoder does not imply a live WebView document.
                # Explicit reopen must reload the chapter after a blank/failed
                # native load, flushing pending position writes first.
                await self.move_book_page(self.book_record['position'])
            return True
        token = self.app.workspace.token(self.session.id)
        await super().open_book(key, password=password)
        if not self.app.active_host or not self.app.workspace.accepts(token):
            self.release_book_reader()
            return False
        if self.book_reader is not None:
            self._reader_suspended = False
        self.session.transient = bool(getattr(getattr(self.book_reader, 'document', None), 'password', None)
                                      or self.book_pending_key is not None)
        if self.manager.active is not self:
            self.suspend()
        self.manager.update_session(self)
        self.app.save_workspace()
        return self.book_reader is not None

    async def display_book_page(self, index):
        await super().display_book_page(index)
        if self.session is not None and self.book_record is not None:
            self.session.view['position'] = self.book_record['position']
        self.manager.update_session(self)

    def cancel_book_unlock(self, widget=None, **kwargs):
        super().cancel_book_unlock(widget, **kwargs)
        self.manager.update_session(self)

    def suspend(self):
        pending = getattr(self, '_epub_location_task', None)
        if self.book_busy or (pending is not None and not pending.done()):
            return False
        if self.book_reader is not None:
            self._reader_suspended = True
            self._suspended_reading_mode = self.reader_immersive
            self.manager.update_session(self)
        self.release_book_reader()
        self.hide_book_unlock()
        self.book_status.text = 'Reader suspended. Open this item to continue.'
        self.manager.update_session(self)
        return True


    def _can_resume_visible_reader(self):
        session = self.session
        privacy = self.app.screen_privacy
        return (self.app.active_host and not privacy.inactive
                and not any(gate.locked for gate in privacy.gates())
                and session is not None and session.id in self.app.workspace.sessions
                and self.manager.controllers.get(session.id) is self
                and self.manager.active is self and self.app.visible_reader() == session.id)

    def resume_suspended_page(self):
        """Reopen a trimmed library decoder in the retained reader route."""
        task = getattr(self, '_resume_book_task', None)
        if (not getattr(self, '_reader_suspended', False) or self.book_busy
                or self.book_pending_key is not None or not self._can_resume_visible_reader()
                or (task is not None and not task.done())):
            return
        token = self.app.workspace.token(self.session.id)
        immersive = self._suspended_reading_mode
        self._resume_book_task = self.app.loop.create_task(
            self._resume_after_suspend(token, immersive))
        return self._resume_book_task

    async def _resume_after_suspend(self, token, immersive):
        # Android can deliver repeated wake callbacks, or close/change routes
        # between scheduling this task and the first decoder operation.
        if not self.app.workspace.accepts(token) or not self._can_resume_visible_reader():
            return
        opened = await self.open_book(self.session.resource)
        if not opened:
            return  # Protected archives keep their existing explicit password prompt.
        if self._can_resume_visible_reader() and self.app.workspace.accepts(token):
            self.set_reading_mode(immersive, present=False)
        else:
            self.suspend()


class Readers:
    def __init__(self, app):
        self.app = app
        self.controllers = {}
        self.active = None
        self.catalog = ReaderController(self)
        self.catalog.show_library(present=False)

    def bind(self, owner):
        for other in self.controllers.values():
            if other is not owner and getattr(other, 'book_reader', None) is not None:
                other.suspend()
        self.active = owner
        if owner.session is not None:
            self.app.workspace.activate(owner.session.id)
        self.update_session(owner)

    def update_session(self, owner):
        if owner.session is not None and owner.book_record is not None:
            owner.session.view['position'] = owner.book_record['position']

    def show_catalog(self):
        self.catalog.presentation_destination = self.app.native_host.state.destination
        self.catalog.refresh_library()
        self.catalog.show_library()

    async def open(self, resource, *, password=None, destination=None):
        import asyncio
        destination = destination or self.app.native_host.state.destination
        loading = getattr(self.app, '_file_loading', None)
        deferred = loading is not None and loading['task'] is asyncio.current_task()
        manager = getattr(self.app, 'scene_manager', None)
        if password is not None and manager is not None and len(manager.owners.hosts) > 1:
            raise ValueError('Close other windows before opening protected content.')
        if not self.app.checkpoint():
            return False
        record = self.catalog.library_store.read_record(resource)[0]
        if not self.app.require_document_feature(record['name'], kind=record['kind']):
            return False
        existing = next((value for value in self.app.workspace.sessions.values()
                         if value.identity == ('library', resource)), None)
        session = self.app.workspace.open('library', resource, record['kind'], record['name'],
                                         transient=existing.transient if existing else False)
        owner = self.controllers.get(session.id)
        if owner is None:
            owner = ReaderController(self, session)
            owner.presentation_destination = destination
            self.controllers[session.id] = owner
            owner.show_library(present=not deferred)
            # Each view owns its decoder; the catalog owns the shared storage
            # adapter, including the native archive implementation.
            owner.library_store = self.catalog.library_store
            owner.refresh_library()
        else:
            owner.presentation_destination = destination
            self.bind(owner)
            owner.show_library(present=not deferred)
        if deferred:
            self.bind(owner)
        navigation = self.app.navigation_generation
        selection = self.app.workspace.active
        opened = await owner.open_book(resource, password=password)
        if (deferred and (opened or owner.book_pending_key is not None)
                and self.app.active_host and self.app.navigation_generation == navigation
                and self.app.workspace.active == selection
                and self.app.native_host.state.destination == destination):
            owner.show_library()
        return opened

    def close(self, key):
        owner = self.controllers.get(key)
        pending = getattr(owner, '_epub_location_task', None)
        if owner is not None and (owner.book_busy or (pending is not None and not pending.done())):
            owner.request_position_flush()
            owner.book_status.text = 'Wait for this reader operation before closing.'
            return False
        if not self.app.workspace.close(key, guard=lambda session: True):
            return False
        if owner is not None:
            owner.suspend()
            self.controllers.pop(key, None)
        if self.active is owner:
            self.active = self.catalog
            self.update_session(self.catalog)
        self.app.save_workspace()
        self.app.reader_closed(key)
        return True


class ReaderWorkspace:
    def reader_manager(self):
        if not hasattr(self, 'readers'):
            self.readers = Readers(self)
        return self.readers

    def show_library(self, widget=None, **kwargs):
        if not self.feature_enabled('books') and not self.feature_enabled('comics'):
            self.require_feature('books')
            return
        self.reader_manager().show_catalog()

    def refresh_library(self):
        manager = self.reader_manager()
        manager.catalog.refresh_library()
        if manager.active is not None:
            manager.active.refresh_library()
            manager.update_session(manager.active)

    async def open_book(self, key, *, password=None, destination=None):
        import asyncio
        from .document_sources import opening_status
        manager = self.reader_manager()
        record = manager.catalog.library_store.read_record(key)[0]
        with opening_status(self, dict(key=record['name']), destination=destination):
            await asyncio.sleep(0)
            return await manager.open(key, password=password, destination=destination)

    async def import_book(self, widget=None, **kwargs):
        return await self.reader_manager().active.import_book(widget, **kwargs)

    async def next_book_page(self, widget=None, **kwargs):
        return await self.reader_manager().active.next_book_page(widget, **kwargs)

    async def previous_book_page(self, widget=None, **kwargs):
        return await self.reader_manager().active.previous_book_page(widget, **kwargs)

    async def toggle_bookmark(self, widget=None, **kwargs):
        return await self.reader_manager().active.toggle_bookmark(widget, **kwargs)

    async def unlock_book(self, widget=None, **kwargs):
        return await self.reader_manager().active.unlock_book(widget, **kwargs)

    def cancel_book_unlock(self, widget=None, **kwargs):
        return self.reader_manager().active.cancel_book_unlock(widget, **kwargs)
