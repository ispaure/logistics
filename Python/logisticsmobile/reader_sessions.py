"""Library-session controllers retain identity while inactive decoders suspend."""
from .reader_ui import ReaderUI
from .reader_host import ReaderHost


class ReaderController(ReaderHost, ReaderUI):
    def __init__(self, manager, session=None):
        self.manager, self.app, self.session = manager, manager.app, session
        self.presentation_destination = 'documents'

    def show_view(self, view, **kwargs):
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
            return True
        token = self.app.workspace.token(self.session.id)
        await super().open_book(key, password=password)
        if not self.app.active_host or not self.app.workspace.accepts(token):
            self.release_book_reader()
            return False
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

    def lock_book(self, widget=None, **kwargs):
        if self.session is not None:
            self.app.workspace.invalidate(self.session.id)
        super().lock_book(widget, **kwargs)
        self.manager.update_session(self)

    def cancel_book_unlock(self, widget=None, **kwargs):
        super().cancel_book_unlock(widget, **kwargs)
        self.manager.update_session(self)

    def suspend(self):
        pending = getattr(self, '_epub_location_task', None)
        if self.book_busy or (pending is not None and not pending.done()):
            return False
        self.release_book_reader()
        self.hide_book_unlock()
        self.book_status.text = 'Reader suspended. Open this item to continue.'
        self.manager.update_session(self)
        return True


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
        self.catalog.refresh_library()
        self.catalog.show_library()

    async def open(self, resource, *, password=None, destination='documents'):
        manager = getattr(self.app, 'scene_manager', None)
        if password is not None and manager is not None and len(manager.owners.hosts) > 1:
            raise ValueError('Close other windows before opening protected content.')
        if not self.app.checkpoint():
            return False
        record = self.catalog.library_store.read_record(resource)[0]
        existing = next((value for value in self.app.workspace.sessions.values()
                         if value.identity == ('library', resource)), None)
        session = self.app.workspace.open('library', resource, record['kind'], record['name'],
                                         transient=existing.transient if existing else False)
        owner = self.controllers.get(session.id)
        if owner is None:
            owner = ReaderController(self, session)
            owner.presentation_destination = destination
            self.controllers[session.id] = owner
            owner.show_library()
            # Each view owns its decoder; the catalog owns the shared storage
            # adapter, including the native archive implementation.
            owner.library_store = self.catalog.library_store
            owner.refresh_library()
        else:
            owner.presentation_destination = destination
            self.bind(owner)
            owner.show_library()
        return await owner.open_book(resource, password=password)

    def close(self, key):
        owner = self.controllers.get(key)
        pending = getattr(owner, '_epub_location_task', None)
        if owner is not None and (owner.book_busy or (pending is not None and not pending.done())):
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
        self.app.show_documents_hub()
        return True


class ReaderWorkspace:
    def reader_manager(self):
        if not hasattr(self, 'readers'):
            self.readers = Readers(self)
        return self.readers

    def show_library(self, widget=None, **kwargs):
        self.reader_manager().show_catalog()

    def refresh_library(self):
        manager = self.reader_manager()
        manager.catalog.refresh_library()
        if manager.active is not None:
            manager.active.refresh_library()
            manager.update_session(manager.active)

    async def open_book(self, key, *, password=None, destination='documents'):
        return await self.reader_manager().open(key, password=password, destination=destination)

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

    def lock_book(self, widget=None, **kwargs):
        return self.reader_manager().active.lock_book(widget, **kwargs)

    def cancel_book_unlock(self, widget=None, **kwargs):
        return self.reader_manager().active.cancel_book_unlock(widget, **kwargs)
