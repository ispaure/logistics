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
from .provider_progress import ProgressWrites


class ReaderUI(LibraryCatalog, ReaderChrome):
    def show_library(self, widget=None, *, present=True, **kwargs):
        if present and not self.app.feature_enabled('books') and not self.app.feature_enabled('comics'):
            self.app.require_feature('books')
            return
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
            self.comic_controller().sync_comic_neighbors()
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
                if not self.app.require_document_feature(str(selected[1])):
                    return
                record = await asyncio.to_thread(self.library_store.import_book, *selected)
                self.refresh_library()
                self.set_book_busy(False)
                await self.open_book(record['id'])
        except Exception as error:
            self.book_status.text = 'Book import failed: ' + str(error)[:500]
        finally:
            self.set_book_busy(False)

    @property
    def _epub_location_task(self):
        return getattr(getattr(self, '_book_progress', None), 'task', None)

    def request_position_flush(self):
        progress = getattr(self, '_book_progress', None)
        if progress is not None:
            return progress.schedule(immediate=True)

    def release_book_reader(self):
        progress = getattr(self, '_book_progress', None)
        if progress is not None:
            progress.close()
            self._book_progress = None
        self.format_services.clear_comic_boundary()
        from .page_animation import cancel_page_slide
        cancel_page_slide(self.book_content)
        self.close_read_aloud()
        sidebar = getattr(self, 'chapter_sidebar', None)
        if sidebar is not None:
            sidebar.show_detail()
        self.book_epoch = getattr(self, 'book_epoch', 0) + 1
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
        from .external_display import sync as sync_external
        sync_external(getattr(self, 'app', self))

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
            record, reader, state, restored = await asyncio.to_thread(
                self.library_store.open_reading, key, password=password, app=self.app)
            if epoch != self.book_epoch or not self.active_host:
                state.retire()
                source = getattr(getattr(reader, 'document', None), 'source', None)
                if hasattr(source, 'close'):
                    source.close()
                return
            self.hide_book_unlock()
            self._library_baseline = record
            record = self._restored_record(record, reader, restored)
            self.book_record, self.book_reader = record, reader
            self._book_progress = ProgressWrites(self, state)
            self._book_location = None
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
            await self.display_book_page(min(record['position'], count - 1), initial=True)
            self._book_progress.report_load()
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

    @staticmethod
    def _restored_record(record, reader, restored):
        names = reader.spine if record['kind'] == 'epub' else reader.pages
        resource, index = restored.get('resource'), restored.get('page', 0)
        if type(index) is not int or not 0 <= index < len(names):
            index = 0
        if isinstance(resource, str) and resource in names and names[index] != resource:
            index = names.index(resource)
        record = dict(record, position=index, bookmarks=restored.get('bookmarks', []))
        record.pop('location', None)
        record.pop('comic_half', None)
        if record['kind'] == 'epub':
            from features.books.locations import valid_location
            location = dict(path=names[index], offset=restored.get('offset', 0))
            if valid_location(location):
                record['location'] = location
            record['epub_bookmarks'] = [value for value in restored.get('epub_bookmarks', [])
                                        if valid_location(value)]
        else:
            record['comic_half'] = 1 if restored.get('half') == 1 else 0
        record['bookmarks'] = [value for value in record['bookmarks']
                               if type(value) is int and 0 <= value < len(names)]
        return record

    def observe_book_location(self, index, *, offset=None, initial=False):
        progress = getattr(self, '_book_progress', None)
        if (progress is None or not self.active_host or self.manager.active is not self
                or self.app.visible_reader() != self.session.id):
            return
        reader = self.book_reader
        if offset is None:
            value = dict(page=index, resource=reader.pages[index], half=self.comic_navigation.half)
        else:
            value = dict(page=index, resource=reader.spine[index], offset=offset)
            self.book_record = dict(self.book_record, location=dict(path=reader.spine[index], offset=offset))
        if value != self._book_location:
            self._book_location = value
            if not initial:
                progress.observe(value)

    async def display_book_page(self, index, *, preserve_speech=False, initial=False,
                                speech_chapter=None):
        if not preserve_speech:
            self.close_read_aloud()
        sidebar = getattr(self, 'chapter_sidebar', None)
        if sidebar is not None:
            sidebar.show_detail()
        if self.book_reader is None:
            return
        from .reading.publication import ReadingPublication
        publication = ReadingPublication.library(self)
        reader, record = self.book_reader, self.book_record
        epoch = self.book_epoch
        count = len(reader.spine if record['kind'] == 'epub' else reader.pages)
        if not 0 <= index < count:
            return
        if record['kind'] == 'epub':
            prepared, location = speech_chapter if speech_chapter is not None else (None, None)
            prepared_epub = await self.epub_controller().prepare_page(
                reader, record, index, epoch, prepared=prepared, location=location)
            if prepared_epub is None:
                return
        else:
            prepared = await self.comic_controller().prepare_page(reader, record, index, epoch)
            if prepared is None:
                return
            view, indices, publish = prepared
        if not publication.current():
            return
        location = dict(path=reader.spine[index], offset=prepared_epub[1]) if record['kind'] == 'epub' else None
        updated = dict(record, position=index)
        if location is not None:
            updated['location'] = location
        from .page_animation import page_direction
        direction = 0
        if record['kind'] == 'comic' and self.book_content.children:
            direction = page_direction(record['position'] + self.comic_navigation.half / 2,
                index + self.comic_navigation.prepared[1] / 2,
                right_to_left=getattr(reader, 'right_to_left', False))
        elif record['kind'] == 'epub' and self.book_content.children:
            direction = page_direction(record['position'], index)
        with publication.preparing(direction) as current:
            if not current:
                return
            if record['kind'] == 'epub':
                view = self._prepare_library_epub_view(reader, epoch, index, prepared_epub, initial=initial)
            if not preserve_speech:
                self.close_read_aloud()
            if not publication.mount(view, direction=direction,
                                     publish=publish if record['kind'] == 'comic' else None):
                return
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
        self._project_book_navigation(reader, record, updated, count, index)
        title = reader.title if record['kind'] == 'epub' else record['name']
        direction = ' · Right-to-left manga' if getattr(reader, 'right_to_left', False) else ''
        position = str(index + 1) if record['kind'] == 'epub' or len(indices) == 1 else f'{indices[0] + 1}–{indices[-1] + 1}'
        self.book_status.text = (f'Page {self.comic_navigation.progress_label}{direction}' if record['kind'] == 'comic'
                                 else f'{title} · {position}/{count}{direction}')
        publication.footer(self, comic=record['kind'] == 'comic', count=count, index=index,
                           right_to_left=getattr(reader, 'right_to_left', False),
                           chapter=(self.epub_offset, self.epub_text.length) if record['kind'] == 'epub' else None)
        self.previous_page.enabled = (index > 0 or self.epub_offset > 0) if record['kind'] == 'epub' else self.comic_navigation.can_previous(index)
        self.next_page.enabled = index + 1 < count if record['kind'] == 'epub' else self.comic_navigation.next(index) is not None
        self.book_loading = False
        if record['kind'] == 'comic':
            self.observe_book_location(index, initial=initial)
        elif getattr(view._impl, 'native', None) is None:
            # Host backends mount static HTML without a native navigation bridge.
            self.observe_book_location(index, offset=self.epub_offset, initial=initial)

    def _prepare_library_epub_view(self, reader, epoch, index, prepared_epub, *, initial):
        """Accept callbacks only from the exact chapter currently mounted."""
        from .reading.epub_resume import appearance
        self._epub_appearance = appearance(self.preferences.values)
        self.epub_text, self.epub_offset, content = prepared_epub
        restored_offset = self.epub_offset
        bridge = None

        def event(action, value):
            nonlocal initial
            if bridge is None or self.epub_view._chapter_bridge is not bridge:
                return
            self.epub_event(reader, epoch, index, action, value, initial=initial and value == restored_offset)
            initial = False

        self.epub_view = chapter_view(content, getattr(self, 'epub_view', None), offset=self.epub_offset,
            on_event=event, on_link=lambda href: self.epub_link(reader, epoch, index, href),
            motion_enabled=self.preferences.values.get('android_eink') != 'true')
        bridge = self.epub_view._chapter_bridge
        from .fold_layout import bind_epub_geometry
        bind_epub_geometry(self.epub_view)
        from .font_scaling import bind
        bind(self, self.epub_view, 'epub', web=True)
        from features.books.mobile.pagination import chapter_renderer
        self.page_footer.bind_epub(self.epub_view, reader, index,
            chapter_renderer(reader, self.preferences.values), self.loop,
            length=self.epub_text.length, worker=True)
        view = self.epub_view
        return view

    def _project_book_navigation(self, reader, record, updated, count, index):
        """Project chapter and bookmark controls while the caller suppresses selection."""
        tree = getattr(self, 'chapter_tree', None)
        if tree is not None and tree.current != index:
            tree.current = index
            tree.render()
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

    async def move_book_page(self, index, *, preserve_speech=False, speech_chapter=None, valid=lambda: True):
        pending = getattr(self, '_epub_location_task', None)
        if pending is not None and not pending.done():
            self.request_position_flush()
            await pending
        if self.book_busy or self.book_reader is None or not valid():
            return
        self.set_book_busy(True)
        try:
            kwargs = {'preserve_speech': True} if preserve_speech else {}
            if speech_chapter is not None:
                kwargs['speech_chapter'] = speech_chapter
            await self.display_book_page(index, **kwargs)
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
        if self.book_record and not self.book_busy:
            if self.book_record['kind'] == 'epub' and self.epub_view._chapter_bridge.turn(-1):
                return
            if self.book_record['kind'] == 'comic':
                await self.move_comic(-1)
                return
            await self.move_book_page(self.book_record['position'] - 1)

    async def next_book_page(self, widget=None, **kwargs):
        if self.book_record and not self.book_busy:
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
        record, reader = self.book_record, self.book_reader
        index = record['position']
        marks = list(record['bookmarks'])
        locations = list(record.get('epub_bookmarks', []))
        if record['kind'] == 'epub':
            location = dict(path=reader.spine[index], offset=self.epub_offset)
            if index in marks and self.epub_offset == 0:
                marks.remove(index)
            elif location in locations:
                locations.remove(location)
            elif len(marks) + len(locations) < 200:
                locations.append(location)
        elif index in marks:
            marks.remove(index)
        elif len(marks) < 200:
            marks.append(index)
            marks.sort()
        self.book_record = dict(record, bookmarks=marks, epub_bookmarks=locations)
        count = len(reader.spine if record['kind'] == 'epub' else reader.pages)
        self.book_loading = True
        try:
            self._project_book_navigation(reader, record, self.book_record, count, index)
        finally:
            self.book_loading = False
        progress = self._book_progress
        progress.observe(dict(bookmarks=marks, epub_bookmarks=locations), bookmarks=True)
        await progress.flush()

    def epub_event(self, *args, **kwargs):
        return self.epub_controller().epub_event(*args, **kwargs)

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
            from features.books.library.metadata import values
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
            from features.books.library.metadata import patch
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
            record, updated = await asyncio.to_thread(
                self.library_store.save_metadata, self._library_baseline, reader, changes)
            if self.book_reader is not reader or self.book_epoch != epoch or not self.active_host:
                return
            self._library_baseline = record
            # Metadata edits leave the archive-member revision unchanged.
            self.book_reader = updated
            self.book_record = dict(self.book_record, digest=record['digest'], revision=record['revision'])
            self.book_metadata_initial = edited
            if record['kind'] == 'epub':
                from features.books.library.metadata import values
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
