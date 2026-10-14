"""Native library controls with archive work off the UI thread."""
import asyncio
from uuid import uuid4
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from .library import LibraryStore
from features.books.mobile.content import chapter_html
from features.books.mobile.presentation import chapter_view
from features.comics.mobile.presentation import page_view
from commonUtils.archives.zip_access import ArchivePasswordError
from .reader_chrome import ReaderChrome
from .library_ui import LibraryCatalog
from .reader_controls import page_buttons


class ReaderUI(LibraryCatalog, ReaderChrome):
    def show_library(self, widget=None, *, present=True, **kwargs):
        if not hasattr(self, 'library_store'):
            self.library_store = LibraryStore(self.private_root / 'Library')
            self.book_record = self.book_reader = None
            self.book_busy = False
            self.book_loading = True
            self.book_labels = {}
            self.book_selector = toga.Selection(on_change=self.select_book, style=Pack(height=44))
            self.book_status = toga.Label('Import an EPUB or PNG/JPEG/WebP CBZ comic.', style=Pack(margin_top=8))
            self.book_import = toga.Button('Import book/comic…', on_press=self.import_book, style=Pack(height=44))
            self.book_pending_key = None
            self.book_password = toga.PasswordInput(placeholder='Comic ZIP password', on_confirm=self.unlock_book, style=Pack(height=44))
            self.book_unlock = toga.Button('Unlock comic', on_press=self.unlock_book, style=Pack(flex=1, height=44))
            self.book_unlock_cancel = toga.Button('Cancel', on_press=self.cancel_book_unlock, style=Pack(flex=1, height=44))
            self.book_unlock_panel = toga.Box(children=[self.book_password,
                toga.Box(children=[self.book_unlock, self.book_unlock_cancel], style=Pack(direction=ROW))],
                style=Pack(direction=COLUMN))
            self.book_lock = toga.Button('Lock comic', on_press=self.lock_book, style=Pack(height=44))
            self.book_open = toga.Button('Open selected', on_press=self.open_selected_book, style=Pack(height=44))
            self.book_content = toga.Box(style=Pack(direction=COLUMN, flex=1))
            self.chapter_selector = toga.Selection(on_change=self.select_chapter, style=Pack(height=44))
            self.previous_page, self.next_page = page_buttons(self.previous_book_page, self.next_book_page)
            self.bookmark_button = toga.Button('Bookmark', on_press=self.toggle_bookmark, style=Pack(flex=1, height=44))
            self.bookmark_selector = toga.Selection(on_change=self.select_bookmark, style=Pack(height=44))
            self.library_view = toga.Box(children=[
                toga.Button('All documents', on_press=self.show_documents_hub, style=Pack(height=44)),
                self.book_selector, self.book_import, self.book_open, self.book_lock,
                self.chapter_selector, self.book_content,
                toga.Box(children=[self.previous_page, self.next_page, self.bookmark_button],
                         style=Pack(direction=ROW)), self.bookmark_selector, self.book_status],
                style=Pack(direction=COLUMN, margin=12, flex=1))
            if getattr(self, 'session', None) is not None:
                self.compact_reader()
            else:
                self.build_library_catalog()
            self.refresh_library()
            self.book_loading = False
            self.set_book_busy(False)
        if not hasattr(self.library_view, 'transfer_banner'):
            self.register_transfer_status(self.library_view)
        if present:
            self.show_view(self.library_view, destination='documents', route='library', title='Books & Comics')




    def set_book_busy(self, busy):
        self.book_busy = busy
        for button in getattr(self, 'library_row_buttons', ()):
            button.enabled = not busy
        for control in (self.book_selector, self.book_import, self.book_open, self.chapter_selector,
                        self.previous_page, self.next_page, self.bookmark_button, self.bookmark_selector,
                        self.book_password, self.book_unlock, self.book_unlock_cancel, self.book_lock):
            control.enabled = not busy
        if not busy:
            self.book_open.enabled = bool(self.book_labels)
            self.book_lock.enabled = bool(getattr(getattr(self.book_reader, 'document', None), 'password', None))
            loaded = self.book_record is not None and self.book_reader is not None
            for control in (self.chapter_selector, self.bookmark_button, self.bookmark_selector):
                control.enabled = loaded
            self.previous_page.enabled = loaded and self.book_record['position'] > 0
            count = len(self.book_reader.spine if self.book_record['kind'] == 'epub' else self.book_reader.pages) if loaded else 0
            self.next_page.enabled = loaded and self.book_record['position'] + 1 < count

    async def open_selected_book(self, widget=None, **kwargs):
        if self.book_selector.value in self.book_labels:
            await self.open_book(self.book_labels[self.book_selector.value])

    def select_book(self, widget, **kwargs):
        if not self.book_loading and not self.book_busy and widget.value in self.book_labels:
            self.loop.create_task(self.open_book(self.book_labels[widget.value]))

    async def import_book(self, widget=None, **kwargs):
        from .pickers import pick_document
        if self.book_busy:
            return
        self.set_book_busy(True)
        try:
            selected = await pick_document(self.app)
            if selected:
                record = await asyncio.to_thread(self.library_store.import_book, *selected)
                self.refresh_library()
                self.set_book_busy(False)
                await self.open_book(record['id'])
        except Exception as error:
            self.book_status.text = 'Book import failed: ' + str(error)[:500]
        finally:
            self.set_book_busy(False)

    def release_book_reader(self):
        self.book_epoch = getattr(self, 'book_epoch', 0) + 1
        document = getattr(self.book_reader, 'document', None)
        source = getattr(document, 'source', None)
        if hasattr(source, 'close'):
            source.close()
        if document is not None:
            document.password = None
        self.book_record = self.book_reader = None
        self._comic_mode_started = False
        if hasattr(self, 'reader_immersive'):
            self.set_reading_mode(False, present=False)
        for child in list(self.book_content.children):
            if hasattr(child, 'dispose'):
                child.dispose()
            if hasattr(child, 'image'):
                child.image = None
            self.book_content.remove(child)
        if hasattr(self, 'epub_view'):
            native = getattr(self.epub_view._impl, 'native', None)
            if native is not None:
                native.stopLoading()
            self.epub_view.set_content('https://logistics.invalid/closed-' + uuid4().hex + '/', '<p>Reader closed.</p>')
        self.chapter_selector.items = []
        self.bookmark_selector.items = []

    def hide_book_unlock(self):
        self.book_pending_key = None
        self.book_password.value = ''
        if self.book_unlock_panel in self.library_view.children:
            self.library_view.remove(self.book_unlock_panel)

    def ask_book_password(self, key, message):
        manager = getattr(self, 'scene_manager', None)
        if manager is not None and len(manager.owners.hosts) > 1:
            self.book_status.text = 'Close other windows before opening protected content.'
            return
        self.book_pending_key = key
        self.book_password.value = ''
        if self.book_unlock_panel not in self.library_view.children:
            self.library_view.insert(3, self.book_unlock_panel)
        self.book_status.text = message

    async def unlock_book(self, widget=None, **kwargs):
        if not self.book_busy and self.book_pending_key:
            key, password = self.book_pending_key, self.book_password.value
            self.book_password.value = ''
            await self.open_book(key, password=password)

    def cancel_book_unlock(self, widget=None, **kwargs):
        if not self.book_busy:
            self.hide_book_unlock()
            self.book_status.text = 'Comic unlock cancelled. Its encrypted copy was kept.'

    def lock_book(self, widget=None, **kwargs):
        if not self.book_busy:
            self.book_loading = True
            self.release_book_reader()
            self.hide_book_unlock()
            self.book_loading = False
            self.set_book_busy(False)
            self.book_status.text = 'Comic locked. Open it again to enter its password.'

    async def open_book(self, key, *, password=None):
        if self.book_busy:
            return
        self.set_book_busy(True)
        self.book_status.text = 'Opening…'
        self.book_loading = True
        self.release_book_reader()
        epoch = self.book_epoch
        navigation, selection = self.navigation_generation, self.workspace.active
        try:
            record, reader = await asyncio.to_thread(self.library_store.open, key, password=password)
            if epoch != self.book_epoch or not self.active_host:
                source = getattr(getattr(reader, 'document', None), 'source', None)
                if hasattr(source, 'close'):
                    source.close()
                return
            self.hide_book_unlock()
            self.book_record, self.book_reader = record, reader
            count = len(reader.spine if record['kind'] == 'epub' else reader.pages)
            self.book_loading = True
            if record['kind'] == 'epub':
                names = [next((c.label for c in reader.chapters if c.path == path), f'Chapter {index + 1}')
                         for index, path in enumerate(reader.spine)]
                self.chapter_labels = [f'{index + 1}. {name}' for index, name in enumerate(names)]
            else:
                self.chapter_labels = [f'Page {index + 1}' for index in range(count)]
            self.chapter_selector.items = self.chapter_labels
            self.book_loading = False
            self.refresh_library()
            await self.display_book_page(min(record['position'], count - 1))
        except ArchivePasswordError:
            if epoch != self.book_epoch or not self.active_host:
                return
            self.ask_book_password(key, 'Enter the comic ZIP password.' if not password else
                                   'Password incorrect or archive damaged. Try again.')
        except Exception as error:
            if epoch != self.book_epoch or not self.active_host:
                return
            self.hide_book_unlock()
            self.book_record = self.book_reader = None
            for child in list(self.book_content.children):
                self.book_content.remove(child)
            self.book_status.text = 'Cannot open book: ' + str(error)[:500]
        finally:
            self.book_loading = False
            if self.active_host:
                self.set_book_busy(False)
            else:
                self.book_busy = False
            if (self.active_host and self.book_pending_key is not None
                    and self.native_host.state.destination == self.presentation_destination
                    and self.navigation_generation == navigation and self.workspace.active == selection):
                self.book_password.focus()

    async def display_book_page(self, index):
        if self.book_reader is None:
            return
        reader, record = self.book_reader, self.book_record
        epoch = self.book_epoch
        count = len(reader.spine if record['kind'] == 'epub' else reader.pages)
        if not 0 <= index < count:
            return
        if record['kind'] == 'epub':
            content = await asyncio.to_thread(chapter_html, reader, index,
                int(self.preferences.values['font_size']), margin=int(self.preferences.values['reading_margin']),
                theme=self.preferences.values['reading_theme'])
            if epoch != self.book_epoch or self.book_reader is not reader or not self.active_host:
                return
            self.epub_view = chapter_view(content, getattr(self, 'epub_view', None))
            view = self.epub_view
        else:
            data, mime = await asyncio.to_thread(reader.read_page, index)
            if epoch != self.book_epoch or self.book_reader is not reader or not self.active_host:
                return
            from commonUtils.ui.native.image_canvas import ImageCanvas
            view = page_view(data, canvas=ImageCanvas, on_page=self.swipe_book_page,
                             on_toggle=self.toggle_reading_mode)
        updated = await asyncio.to_thread(self.library_store.progress, record, index)
        if epoch != self.book_epoch or self.book_reader is not reader or not self.active_host:
            return
        for child in list(self.book_content.children):
            if hasattr(child, 'dispose'):
                child.dispose()
            self.book_content.remove(child)
        self.book_content.add(view)
        if record['kind'] == 'comic' and not getattr(self, '_comic_mode_started', False):
            self._comic_mode_started = True
            self.set_reading_mode(True, present=False)
        self.book_record = updated
        self.book_loading = True
        self.chapter_selector.value = self.chapter_labels[index]
        self.bookmark_selector.items = ['Bookmarks…'] + [self.chapter_labels[i] for i in updated['bookmarks'] if i < count]
        self.bookmark_selector.value = 'Bookmarks…'
        self.bookmark_button.text = 'Unbookmark' if index in updated['bookmarks'] else 'Bookmark'
        title = reader.title if record['kind'] == 'epub' else record['name']
        direction = ' · Right-to-left manga' if getattr(reader, 'right_to_left', False) else ''
        self.book_status.text = f'{title} · {index + 1}/{count}{direction}'
        self.previous_page.enabled = index > 0
        self.next_page.enabled = index + 1 < count
        self.book_loading = False

    async def move_book_page(self, index):
        if self.book_busy or self.book_reader is None:
            return
        self.set_book_busy(True)
        try:
            await self.display_book_page(index)
        except Exception as error:
            self.book_status.text = 'Cannot read page: ' + str(error)[:500]
        finally:
            self.book_loading = False
            self.set_book_busy(False)
            self.previous_page.enabled = self.book_record is not None and self.book_record['position'] > 0
            if self.book_record:
                count = len(self.book_reader.spine if self.book_record['kind'] == 'epub' else self.book_reader.pages)
                self.next_page.enabled = self.book_record['position'] + 1 < count

    def select_chapter(self, widget, **kwargs):
        if self.book_loading or self.book_busy or self.book_reader is None:
            return
        try:
            value = widget.value
        except IndexError:
            return
        if value in getattr(self, 'chapter_labels', ()):
            self.loop.create_task(self.move_book_page(self.chapter_labels.index(value)))

    def select_bookmark(self, widget, **kwargs):
        self.select_chapter(widget, **kwargs)

    async def previous_book_page(self, widget=None, **kwargs):
        if self.book_record:
            await self.move_book_page(self.book_record['position'] - 1)

    async def next_book_page(self, widget=None, **kwargs):
        if self.book_record:
            await self.move_book_page(self.book_record['position'] + 1)

    async def toggle_bookmark(self, widget=None, **kwargs):
        if self.book_busy or self.book_record is None:
            return
        self.set_book_busy(True)
        try:
            self.book_record = await asyncio.to_thread(self.library_store.progress, self.book_record,
                self.book_record['position'], bookmark=True)
            await self.display_book_page(self.book_record['position'])
        except Exception as error:
            self.book_status.text = 'Cannot save bookmark: ' + str(error)[:500]
        finally:
            self.set_book_busy(False)
