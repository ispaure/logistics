"""Library-session controllers retain identity while inactive decoders suspend."""
from .library_ui import LibraryUI

FIELDS = ('library_store', 'library_view', 'book_reader', 'book_record', 'book_busy',
          'book_selector', 'book_status', 'book_content', 'book_import', 'book_open',
          'book_password', 'book_unlock', 'book_unlock_cancel', 'book_unlock_panel',
          'book_lock', 'chapter_selector', 'chapter_labels', 'previous_page',
          'next_page', 'bookmark_button', 'bookmark_selector', 'book_pending_key')


class ReaderController(LibraryUI):
    def __init__(self, manager, session=None):
        self.manager, self.app, self.session = manager, manager.app, session

    def __getattr__(self, name):
        if name.startswith(('book_', 'library_', 'chapter_', 'epub_')):
            raise AttributeError(name)
        return getattr(self.app, name)

    def show_view(self, view, **kwargs):
        self.manager.bind(self)
        return self.app.show_view(view, destination='documents',
            route='reader:' + self.session.id if self.session is not None else 'library',
            title=self.session.title if self.session is not None else 'Books & Comics')

    def set_book_busy(self, busy):
        super().set_book_busy(busy)
        self.manager.publish(self)

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
        self.manager.publish(self)
        self.app.save_workspace()
        return self.book_reader is not None

    async def display_book_page(self, index):
        await super().display_book_page(index)
        if self.session is not None and self.book_record is not None:
            self.session.view['position'] = self.book_record['position']
        self.manager.publish(self)

    def lock_book(self, widget=None, **kwargs):
        if self.session is not None:
            self.app.workspace.invalidate(self.session.id)
        super().lock_book(widget, **kwargs)
        self.manager.publish(self)

    def cancel_book_unlock(self, widget=None, **kwargs):
        super().cancel_book_unlock(widget, **kwargs)
        self.manager.publish(self)

    def suspend(self):
        if self.book_busy:
            return False
        self.release_book_reader()
        self.hide_book_unlock()
        self.book_status.text = 'Reader suspended. Open this item to continue.'
        self.manager.publish(self)
        return True


class Readers:
    def __init__(self, app):
        self.app = app
        self.controllers = {}
        self.active = None
        self.catalog = ReaderController(self)
        self.catalog.show_library()

    def bind(self, owner):
        for other in self.controllers.values():
            if other is not owner and getattr(other, 'book_reader', None) is not None:
                other.suspend()
        self.active = owner
        if owner.session is not None:
            self.app.workspace.activate(owner.session.id)
        self.publish(owner)

    def publish(self, owner):
        if self.active is owner:
            for name in FIELDS:
                if hasattr(owner, name):
                    setattr(self.app, name, getattr(owner, name))

    def show_catalog(self):
        self.catalog.refresh_library()
        self.catalog.show_library()

    async def open(self, resource, *, password=None):
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
            self.controllers[session.id] = owner
            owner.show_library()
            # Each view owns its decoder; the catalog owns the shared storage
            # adapter, including the native archive implementation.
            owner.library_store = self.catalog.library_store
            owner.refresh_library()
        else:
            self.bind(owner)
            owner.show_library()
        return await owner.open_book(resource, password=password)

    def close(self, key):
        owner = self.controllers.get(key)
        if owner is not None and owner.book_busy:
            owner.book_status.text = 'Wait for this reader operation before closing.'
            return False
        if not self.app.workspace.close(key, guard=lambda session: True):
            return False
        if owner is not None:
            owner.suspend()
            self.controllers.pop(key, None)
        if self.active is owner:
            self.active = self.catalog
            self.publish(self.catalog)
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
            manager.publish(manager.active)

    async def open_book(self, key, *, password=None):
        return await self.reader_manager().open(key, password=password)

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
