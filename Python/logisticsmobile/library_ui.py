"""Native library controls with archive work off the UI thread."""
import asyncio
from uuid import uuid4
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from .library import LibraryStore
from .reading import chapter_html, image_dimensions


class LibraryUI:
    def show_library(self, widget=None, **kwargs):
        if not hasattr(self, 'library_store'):
            self.library_store = LibraryStore(self.private_root / 'Library')
            self.book_record = self.book_reader = None
            self.book_busy = False
            self.book_loading = True
            self.book_labels = {}
            self.book_selector = toga.Selection(on_change=self.select_book, style=Pack(height=44))
            self.book_status = toga.Label('Import an EPUB or PNG/JPEG CBZ comic.', style=Pack(margin_top=8))
            self.book_import = toga.Button('Import book/comic…', on_press=self.import_book, style=Pack(height=44))
            self.book_open = toga.Button('Open selected', on_press=self.open_selected_book, style=Pack(height=44))
            self.book_content = toga.Box(style=Pack(direction=COLUMN, flex=1))
            self.chapter_selector = toga.Selection(on_change=self.select_chapter, style=Pack(height=44))
            self.previous_page = toga.Button('Previous', on_press=self.previous_book_page, style=Pack(flex=1, height=44))
            self.next_page = toga.Button('Next', on_press=self.next_book_page, style=Pack(flex=1, height=44))
            self.bookmark_button = toga.Button('Bookmark', on_press=self.toggle_bookmark, style=Pack(flex=1, height=44))
            self.bookmark_selector = toga.Selection(on_change=self.select_bookmark, style=Pack(height=44))
            self.library_view = toga.Box(children=[self.book_selector, self.book_import, self.book_open,
                self.chapter_selector, self.book_content,
                toga.Box(children=[self.previous_page, self.next_page, self.bookmark_button],
                         style=Pack(direction=ROW)), self.bookmark_selector, self.book_status],
                style=Pack(direction=COLUMN, margin=12, flex=1))
            self.refresh_library()
            self.book_loading = False
            self.set_book_busy(False)
        self.show_view(self.library_view)

    def refresh_library(self):
        previous = self.book_loading
        self.book_loading = True
        records, failures = self.library_store.items()
        labels = {}
        for record in records:
            label = record['name']
            while label in labels:
                label += ' (copy)'
            labels[label] = record['id']
        self.book_labels = labels
        self.book_selector.items = list(labels)
        if self.book_record:
            self.book_selector.value = next((label for label, key in labels.items()
                                            if key == self.book_record['id']), None)
        if failures:
            self.book_status.text = f'{len(failures)} library record(s) could not be read; they were preserved.'
        self.book_loading = previous

    def set_book_busy(self, busy):
        self.book_busy = busy
        for control in (self.book_selector, self.book_import, self.book_open, self.chapter_selector,
                        self.previous_page, self.next_page, self.bookmark_button, self.bookmark_selector):
            control.enabled = not busy
        if not busy:
            self.book_open.enabled = bool(self.book_labels)
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
            selected = await pick_document(self)
            if selected:
                record = await asyncio.to_thread(self.library_store.import_book, *selected)
                self.refresh_library()
                self.set_book_busy(False)
                await self.open_book(record['id'])
        except Exception as error:
            self.book_status.text = 'Book import failed: ' + str(error)[:500]
        finally:
            self.set_book_busy(False)

    async def open_book(self, key):
        if self.book_busy:
            return
        self.set_book_busy(True)
        self.book_status.text = 'Opening…'
        try:
            record, reader = await asyncio.to_thread(self.library_store.open, key)
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
        except Exception as error:
            self.book_record = self.book_reader = None
            for child in list(self.book_content.children):
                self.book_content.remove(child)
            self.book_status.text = 'Cannot open book: ' + str(error)[:500]
        finally:
            self.book_loading = False
            self.set_book_busy(False)

    async def display_book_page(self, index):
        if self.book_reader is None:
            return
        reader, record = self.book_reader, self.book_record
        count = len(reader.spine if record['kind'] == 'epub' else reader.pages)
        if not 0 <= index < count:
            return
        if record['kind'] == 'epub':
            content = await asyncio.to_thread(chapter_html, reader, index,
                                              int(self.preferences.values['font_size']))
            if not hasattr(self, 'epub_view'):
                self.epub_view = toga.WebView(on_navigation_starting=lambda widget, url, **kw: False, style=Pack(flex=1))
            view = self.epub_view
            view.set_content('https://logistics.invalid/' + uuid4().hex + '/', content)
        else:
            data, mime = await asyncio.to_thread(reader.read_page, index)
            image_dimensions(data)
            view = toga.ImageView(image=toga.Image(src=data), style=Pack(flex=1))
        updated = await asyncio.to_thread(self.library_store.progress, record, index)
        for child in list(self.book_content.children):
            self.book_content.remove(child)
        self.book_content.add(view)
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
        if not self.book_loading and not self.book_busy and widget.value in getattr(self, 'chapter_labels', ()):
            self.loop.create_task(self.move_book_page(self.chapter_labels.index(widget.value)))

    def select_bookmark(self, widget, **kwargs):
        if not self.book_loading and not self.book_busy and widget.value in getattr(self, 'chapter_labels', ()):
            self.loop.create_task(self.move_book_page(self.chapter_labels.index(widget.value)))

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
