"""Native library controls with archive work off the UI thread."""
from commonUtils.ui.native.password_input import PasswordInput
import asyncio
from uuid import uuid4
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from .library import LibraryStore
from features.books.locations import contents
from features.books.mobile.presentation import chapter_view
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
            self.book_password = PasswordInput(placeholder='Comic ZIP password', on_confirm=self.unlock_book, style=Pack(height=44))
            self.book_unlock = toga.Button('Unlock comic', on_press=self.unlock_book, style=Pack(flex=1, height=44))
            self.book_unlock_cancel = toga.Button('Cancel', on_press=self.cancel_book_unlock, style=Pack(flex=1, height=44))
            self.book_unlock_panel = toga.Box(children=[self.book_password,
                toga.Box(children=[self.book_unlock, self.book_unlock_cancel], style=Pack(direction=ROW))],
                style=Pack(direction=COLUMN))
            self.book_open = toga.Button('Open selected', on_press=self.open_selected_book, style=Pack(height=44))
            self.book_content = toga.Box(style=Pack(direction=COLUMN, flex=1))
            self.chapter_selector = toga.Selection(on_change=self.select_chapter, style=Pack(height=44))
            self.previous_page, self.next_page = page_buttons(self.previous_book_page, self.next_book_page)
            self.bookmark_button = toga.Button('Bookmark', on_press=self.toggle_bookmark, style=Pack(flex=1, height=44))
            self.bookmark_selector = toga.Selection(on_change=self.select_bookmark, style=Pack(height=44))
            self.library_view = toga.Box(children=[
                toga.Button('All documents', on_press=self.show_documents_hub, style=Pack(height=44)),
                self.book_selector, self.book_import, self.book_open,
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
            title = self.session.title if getattr(self, 'session', None) is not None else 'Books & Comics'
            self.show_view(self.library_view, route='library', title=title)




    def set_book_busy(self, busy):
        self.book_busy = busy
        if not busy:
            from .layout_events import notify_layout
            notify_layout(self.app)
        if not hasattr(self, '_book_idle'):
            self._book_idle = asyncio.Event()
        if busy:
            self._book_idle.clear()
        else:
            self._book_idle.set()
        header = getattr(self, 'comic_header', None)
        if header is not None:
            from features.comics.mobile.navigation import adjacent_comic
            records = [(record['id'], record['name']) for record in getattr(self, 'imported_records', ())
                       if record['kind'] == 'comic']
            key = self.session.resource
            header.sync(not busy and adjacent_comic(records, key, -1) is not None,
                        not busy and adjacent_comic(records, key, 1) is not None)
        for button in getattr(self, 'library_row_buttons', ()):
            button.enabled = not busy
        if hasattr(self, 'library_folder_list'):
            self.library_folder_list.enabled = not busy
        for control in (self.book_selector, self.book_import, self.book_open, self.chapter_selector,
                        self.previous_page, self.next_page, self.bookmark_button, self.bookmark_selector,
                        self.book_password, self.book_unlock, self.book_unlock_cancel):
            control.enabled = not busy
        if not busy:
            self.book_open.enabled = bool(self.book_labels)
            loaded = self.book_record is not None and self.book_reader is not None
            for control in (self.chapter_selector, self.bookmark_button, self.bookmark_selector):
                control.enabled = loaded
            self.previous_page.enabled = loaded and ((self.book_record['position'] > 0 or getattr(self, 'epub_offset', 0) > 0) if self.book_record['kind'] == 'epub' else self.comic_navigation.can_previous(self.book_record['position']))
            count = len(self.book_reader.spine if self.book_record['kind'] == 'epub' else self.book_reader.pages) if loaded else 0
            if loaded and self.book_record['kind'] == 'epub':
                bridge = self.epub_view._chapter_bridge
                self.next_page.enabled = self.book_record['position'] + 1 < count or (bridge.ready and not bridge.at_end)
            else:
                self.next_page.enabled = loaded and self.comic_navigation.next(self.book_record['position']) is not None

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
        from .page_animation import cancel_page_slide
        cancel_page_slide(self.book_content)
        self.close_read_aloud()
        self.book_epoch = getattr(self, 'book_epoch', 0) + 1
        self._epub_pending = None
        for name in ('_comic_layout_task', '_epub_width_task'):
            task = getattr(self, name, None)
            if task is not None:
                task.cancel()
        if hasattr(self, 'epub_view') and hasattr(self.epub_view, '_chapter_bridge'):
            self.epub_view._chapter_bridge.dispose()
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
                from features.books.mobile.navigation import chapter_labels
                self.chapter_labels = chapter_labels(reader)
            else:
                self.chapter_labels = [f'Page {index + 1}' for index in range(count)]
            self.contents_choices = {}
            if record['kind'] == 'epub':
                self.contents_choices = {
                    f'{number + 1}. ' + '  ' * entry.depth + entry.label: entry
                    for number, entry in enumerate(contents(reader))}
            self.chapter_selector.items = list(self.contents_choices) or self.chapter_labels
            if record['kind'] == 'epub':
                self.chapter_collapsed.clear()
                self.render_chapters()
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
        self.close_read_aloud()
        if self.book_reader is None:
            return
        reader, record = self.book_reader, self.book_record
        epoch = self.book_epoch
        count = len(reader.spine if record['kind'] == 'epub' else reader.pages)
        if not 0 <= index < count:
            return
        if record['kind'] == 'epub':
            prepared_epub = await self.epub_controller().prepare_page(reader, record, index, epoch)
            if prepared_epub is None:
                return
        else:
            prepared = await self.comic_controller().prepare_page(reader, record, index, epoch)
            if prepared is None:
                return
            view, indices = prepared
        location = dict(path=reader.spine[index], offset=prepared_epub[1]) if record['kind'] == 'epub' else None
        updated = dict(record, position=index)
        if location is not None:
            updated['location'] = location
        from .page_animation import page_direction, begin_page_slide, finish_page_slide
        direction = 0
        if record['kind'] == 'comic' and self.book_content.children:
            direction = page_direction(record['position'] + self.comic_navigation.half / 2,
                index + self.comic_navigation.prepared[1] / 2,
                right_to_left=getattr(reader, 'right_to_left', False))
        elif record['kind'] == 'epub' and self.book_content.children:
            direction = page_direction(record['position'], index)
        begin_page_slide(self.book_content, direction, self.preferences.values)
        if record['kind'] == 'epub':
            self.epub_text, self.epub_offset, content = prepared_epub
            self.epub_view = chapter_view(content, getattr(self, 'epub_view', None), offset=self.epub_offset,
                on_event=lambda action, value: self.epub_event(reader, epoch, index, action, value),
                on_link=lambda href: self.epub_link(reader, epoch, index, href))
            from .font_scaling import bind
            bind(self, self.epub_view, 'epub', web=True)
            view = self.epub_view
        for child in list(self.book_content.children):
            if child is not view and hasattr(child, 'dispose'):
                child.dispose()
            self.book_content.remove(child)
        self.close_read_aloud()
        self.book_content.add(view)
        finish_page_slide(self.book_content, direction, self.preferences.values)
        if record['kind'] == 'comic':
            from .magnifier import bind
            bind(self, view)
            view.magnifier_enabled = self.reader_immersive
        if record['kind'] == 'epub':
            self.watch_epub_width(reader, epoch)
        if record['kind'] == 'comic':
            self.comic_navigation.commit(indices)
            updated['comic_half'] = self.comic_navigation.half
            self.watch_comic_layout(reader, epoch)
        if record['kind'] == 'comic' and not getattr(self, '_comic_mode_started', False):
            self._comic_mode_started = True
            self.set_reading_mode(True, present=False)
        self.book_record = updated
        self.book_loading = True
        self.chapter_selector.value = next((label for label, entry in self.contents_choices.items()
            if entry.index == index), self.chapter_labels[index]) if self.contents_choices else self.chapter_labels[index]
        self.bookmark_selector.items = ['Bookmarks…'] + [self.chapter_labels[i] for i in updated['bookmarks'] if i < count]
        self.epub_bookmark_choices = {}
        if record['kind'] == 'epub':
            for number, location in enumerate(updated.get('epub_bookmarks', [])):
                if location['path'] in reader.spine:
                    chapter = reader.spine.index(location['path'])
                    label = f'{number + 1}. {self.chapter_labels[chapter]} · text {location["offset"]}'
                    self.epub_bookmark_choices[label] = location
            self.bookmark_selector.items = ['Bookmarks…'] + [self.chapter_labels[i] for i in updated['bookmarks'] if i < count] + list(self.epub_bookmark_choices)
        self.bookmark_selector.value = 'Bookmarks…'
        marked = ((dict(path=reader.spine[index], offset=self.epub_offset) in updated.get('epub_bookmarks', []))
                  or (self.epub_offset == 0 and index in updated['bookmarks'])) if record['kind'] == 'epub' else index in updated['bookmarks']
        self.bookmark_button.text = 'Unbookmark' if marked else 'Bookmark'
        title = reader.title if record['kind'] == 'epub' else record['name']
        direction = ' · Right-to-left manga' if getattr(reader, 'right_to_left', False) else ''
        position = str(index + 1) if record['kind'] == 'epub' or len(indices) == 1 else f'{indices[0] + 1}–{indices[-1] + 1}'
        self.book_status.text = (f'Page {position}/{count}{self.comic_navigation.part_label}{direction}' if record['kind'] == 'comic'
                                 else f'{title} · {position}/{count}{direction}')
        if hasattr(self, 'page_footer'):
            self.page_footer.sync(comic=record['kind'] == 'comic', count=count, index=index,
                                  right_to_left=getattr(reader, 'right_to_left', False))
            if record['kind'] == 'epub':
                self.page_footer.chapter_progress(index, count, self.epub_offset, self.epub_text.length)
        self.previous_page.enabled = (index > 0 or self.epub_offset > 0) if record['kind'] == 'epub' else self.comic_navigation.can_previous(index)
        self.next_page.enabled = index + 1 < count if record['kind'] == 'epub' else self.comic_navigation.next(index) is not None
        self.book_loading = False
        # Initial EPUB content arrives after its reader route was presented.
        from .reader_chrome import sync_comic_chrome
        sync_comic_chrome(self.app, self.app.body)
        # Mount the prepared page before filesystem latency; the loop can paint
        # while the worker publishes ordinary imported-library progress.
        try:
            saved = await asyncio.to_thread(self.library_store.progress, record, index, location=location,
                **({'comic_half': self.comic_navigation.half} if record['kind'] == 'comic' else {}))
            if self.book_reader is reader and self.book_epoch == epoch and self.book_record['position'] == index:
                self.book_record = saved
        except (OSError, ValueError) as error:
            if self.book_reader is reader and self.book_epoch == epoch:
                self.book_status.text = 'Cannot save reading position: ' + str(error)[:300]

    async def move_book_page(self, index):
        pending = getattr(self, '_epub_location_task', None)
        if pending is not None and not pending.done():
            self.request_position_flush()
            await pending
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

    def select_chapter(self, widget, **kwargs):
        if self.book_loading or self.book_busy or self.book_reader is None:
            return
        try:
            value = widget.value
        except IndexError:
            return
        if value in getattr(self, 'contents_choices', {}):
            entry = self.contents_choices[value]
            self._epub_target = entry.fragment
            self.loop.create_task(self.open_reader_destination(entry.index))
        elif value in getattr(self, 'chapter_labels', ()):
            self.loop.create_task(self.open_reader_destination(self.chapter_labels.index(value)))

    async def open_reader_destination(self, index):
        await self.move_book_page(index)
        if (self.active_host and self.book_reader is not None and self.manager.active is self
                and self.book_record['position'] == index):
            self.show_library()

    def select_bookmark(self, widget, **kwargs):
        try:
            value = widget.value
        except IndexError:
            return
        location = getattr(self, 'epub_bookmark_choices', {}).get(value)
        if location is not None and not self.book_busy and self.book_reader is not None:
            self._epub_target = location['offset']
            self.loop.create_task(self.open_reader_destination(self.book_reader.spine.index(location['path'])))
        else:
            self.select_chapter(widget, **kwargs)

    async def previous_book_page(self, widget=None, **kwargs):
        if self.book_record:
            if self.book_record['kind'] == 'epub' and self.epub_view._chapter_bridge.turn(-1):
                return
            if self.book_record['kind'] == 'comic':
                await self.move_comic(-1)
                return
            await self.move_book_page(self.book_record['position'] - 1)

    async def next_book_page(self, widget=None, **kwargs):
        if self.book_record:
            if self.book_record['kind'] == 'epub' and self.epub_view._chapter_bridge.turn(1):
                return
            if self.book_record['kind'] == 'comic':
                await self.move_comic(1)
                return
            await self.move_book_page(self.book_record['position'] + 1)

    async def toggle_bookmark(self, widget=None, **kwargs):
        pending = getattr(self, '_epub_location_task', None)
        if pending is not None and not pending.done():
            self.request_position_flush()
            await pending
        if self.book_busy or self.book_record is None:
            return
        self.set_book_busy(True)
        try:
            self.book_record = await asyncio.to_thread(self.library_store.progress, self.book_record,
                self.book_record['position'], bookmark=True,
                location=dict(path=self.book_reader.spine[self.book_record['position']], offset=self.epub_offset)
                    if self.book_record['kind'] == 'epub' else None)
            await self.display_book_page(self.book_record['position'])
        except Exception as error:
            self.book_status.text = 'Cannot save bookmark: ' + str(error)[:500]
        finally:
            self.set_book_busy(False)

    def epub_event(self, *args, **kwargs):
        return self.epub_controller().epub_event(*args, **kwargs)

    def request_position_flush(self, *args, **kwargs):
        return self.epub_controller().request_position_flush(*args, **kwargs)

    async def save_epub_location(self, *args, **kwargs):
        return await self.epub_controller().save_epub_location(*args, **kwargs)

    async def epub_boundary(self, *args, **kwargs):
        return await self.epub_controller().epub_boundary(*args, **kwargs)

    def epub_link(self, *args, **kwargs):
        return self.epub_controller().epub_link(*args, **kwargs)

    def show_epub_search(self, *args, **kwargs):
        return self.epub_controller().show_epub_search(*args, **kwargs)

    async def find_epub_next(self, *args, **kwargs):
        return await self.epub_controller().find_epub_next(*args, **kwargs)


    def comic_seam(self, *args, **kwargs):
        return self.comic_controller().comic_seam(*args, **kwargs)

    def comic_layout_mode(self, *args, **kwargs):
        return self.comic_controller().comic_layout_mode(*args, **kwargs)

    def comic_viewport(self, *args, **kwargs):
        return self.comic_controller().comic_viewport(*args, **kwargs)

    async def move_comic(self, *args, **kwargs):
        return await self.comic_controller().move_comic(*args, **kwargs)


    async def adjacent_book_comic(self, *args, **kwargs):
        return await self.comic_controller().adjacent_book_comic(*args, **kwargs)

    async def previous_comic_file(self, *args, **kwargs):
        return await self.comic_controller().previous_comic_file(*args, **kwargs)

    async def next_comic_file(self, *args, **kwargs):
        return await self.comic_controller().next_comic_file(*args, **kwargs)


    def show_book_metadata(self, widget=None, **kwargs):
        if self.book_busy or self.book_reader is None:
            return
        if getattr(self, 'book_metadata_fields', None) and hasattr(self, 'book_metadata_view'):
            self.show_view(self.book_metadata_view, reader_route='metadata', title='Edit metadata')
            return
        if self.book_record['kind'] == 'epub':
            from features.books.mobile.metadata import values
            self.book_metadata_initial, self.book_metadata_original = values(self.book_reader)
        else:
            from features.comics.mobile.metadata import values
            self.book_metadata_initial = values(self.book_reader.document)
        self.book_metadata_fields = {key: toga.MultilineTextInput(value=value, style=Pack(height=80))
            for key, value in self.book_metadata_initial.items()}
        self.book_metadata_status = toga.Label('Saves update the imported copy; the original import source is unchanged.')
        choices = {}
        if self.book_record['kind'] == 'comic':
            catalog = self.manager.catalog
            if getattr(catalog, 'metadata_ready', False):
                choices = catalog.metadata_index.suggestions()
        children = [self.book_metadata_status]
        for key, field in self.book_metadata_fields.items():
            children.extend([toga.Label(key), field])
            if choices.get(key):
                from features.comics.mobile.metadata import suggestion_picker
                children.append(suggestion_picker(key, field, choices[key]))
        children.extend([toga.Button('Save metadata', on_press=self.save_book_metadata, style=Pack(height=44)),
            toga.Button('Return to reading', on_press=self.show_library, style=Pack(height=44))])
        self.book_metadata_view = toga.ScrollContainer(horizontal=False, content=toga.Box(children=children,
            style=Pack(direction=COLUMN, margin=12)), style=Pack(flex=1))
        self.show_view(self.book_metadata_view, reader_route='metadata', title='Edit metadata')

    async def save_book_metadata(self, widget=None, **kwargs):
        pending = getattr(self, '_epub_location_task', None)
        if pending is not None and not pending.done():
            self.request_position_flush()
            await pending
        if self.book_busy or self.book_reader is None:
            return
        edited = {key: field.value for key, field in self.book_metadata_fields.items()}
        if self.book_record['kind'] == 'epub':
            from features.books.mobile.metadata import patch
            changes = patch(self.book_metadata_initial, edited, self.book_metadata_original)
        else:
            from features.comics.mobile.metadata import patch
            changes = patch(self.book_metadata_initial, edited)
        if not changes:
            self.book_metadata_status.text = 'No changes to save.'
            return
        self.set_book_busy(True)
        for field in self.book_metadata_fields.values():
            field.readonly = True
        try:
            index, reader, epoch = self.book_record['position'], self.book_reader, self.book_epoch
            record, updated = await asyncio.to_thread(self.library_store.save_metadata, self.book_record, reader, changes)
            if self.book_reader is not reader or self.book_epoch != epoch or not self.active_host:
                return
            self.book_reader, self.book_record = updated, record
            self.book_metadata_initial = edited
            if record['kind'] == 'epub':
                from features.books.mobile.metadata import values
                self.book_metadata_initial, self.book_metadata_original = values(updated)
            for key, field in self.book_metadata_fields.items():
                field.value = self.book_metadata_initial[key]
            await self.display_book_page(index)
            self.book_metadata_status.text = 'Metadata saved to the imported copy.'
            self.refresh_library()
            if self.manager.catalog is not self:
                self.manager.catalog.refresh_library()
        except Exception as error:
            self.book_metadata_status.text = 'Save failed; edits retained: ' + str(error)[:300]
        finally:
            for field in self.book_metadata_fields.values():
                field.readonly = False
            self.set_book_busy(False)


    def watch_epub_width(self, *args, **kwargs):
        return self.epub_controller().watch_epub_width(*args, **kwargs)

    def watch_comic_layout(self, *args, **kwargs):
        return self.comic_controller().watch_comic_layout(*args, **kwargs)

    async def first_comic_page(self, *args, **kwargs):
        return await self.comic_controller().first_comic_page(*args, **kwargs)

    async def last_comic_page(self, *args, **kwargs):
        return await self.comic_controller().last_comic_page(*args, **kwargs)
