"""App-hosted provider documents: private drafts, format views and session controls."""
import asyncio
import threading
import textwrap
from pathlib import Path
import toga
from .control_icons import icon_button
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

def speech_session_valid(owner):
    if not owner.active_host or owner.crypt_reader is None:
        return False
    store = owner._crypt_reader_store
    if getattr(store, 'encrypted', True) or getattr(store, 'remote_storage', False):
        return owner.credential_generation == getattr(owner.credential_client, 'generation', None)
    return True


def private_label(value):
    # Native labels use their longest line as a minimum width. Bound messages
    # and virtual filenames so they cannot widen a phone's entire reader.
    return textwrap.fill(str(value), width=30)


from commonUtils.runtime.operations import check_cancelled


from .files_ui import FilesUI
from .reader_controls import ReadingFrame, PageFooter, page_buttons, schedule_swipe


class ProviderUI(FilesUI):

    def private_dirty(self):
        return bool(self.crypt_reader and ((self.crypt_reader.editable and self.crypt_text.value != self.crypt_reader.text)
                    or any(field.value != self.crypt_metadata_initial[key] for key, field in self.crypt_metadata_fields.items())))

    def resume_crypt(self, widget=None, **kwargs):
        if self.crypt_reader is not None:
            self.show_view(self.crypt_view, destination='documents')

    def clear_private_reader(self, *, discard=False):
        if getattr(self, '_crypt_cancel', None) is not None:
            return False
        if self.private_dirty() and not discard:
            self.crypt_title.text = private_label('Unsaved changes: save, or discard and close.')
            self.resume_crypt()
            return False
        for name in ('_provider_layout_task', '_provider_width_task'):
            task = getattr(self, name, None)
            if task is not None:
                task.cancel()
                setattr(self, name, None)
        if hasattr(self, 'provider_epub_view'):
            self.provider_epub_view.dispose()
            del self.provider_epub_view
        self._provider_epub_locations = {}
        search = getattr(self, 'pdf_search', None)
        if search is not None:
            search.dispose()
        contents = getattr(self, 'pdf_contents', None)
        if contents is not None:
            contents.dispose()
        reader = self.crypt_reader
        if reader is not None and reader.kind == '.pdf':
            reader.pdf.close()
            reader.data = b''
            from services.documents.readers import MemorySource
            if isinstance(reader.source, MemorySource):
                reader.source.data = b''
        self.crypt_reader = None
        for field in self.crypt_metadata_fields.values():
            field.value = ''
        self.crypt_metadata_fields = {}
        self.crypt_metadata_initial = {}
        self.crypt_metadata_values = {}
        if hasattr(self, 'crypt_metadata_view'):
            self.crypt_metadata_view.content = None
            self.crypt_metadata_status.text = ''
        self.clear_private_preview()
        preview = getattr(self, 'crypt_preview', None)
        if preview is not None:
            from features.text_editor.mobile.markdown_editor import retire_webview
            retire_webview(preview)
            self.crypt_preview = None
        if hasattr(self, 'crypt_text'):
            self.crypt_text.value = ''
            dispose = getattr(self.crypt_text, 'dispose', None)
            if dispose is not None:
                dispose()
        if hasattr(self, 'provider_spread'):
            self.provider_spread.dispose()
        if hasattr(self, 'crypt_image'):
            self.crypt_image.dispose()
        if hasattr(self, 'crypt_page'):
            self.crypt_page.items = []
        if hasattr(self, 'epub_session_bookmarks'):
            self.epub_session_bookmarks.clear()
        if hasattr(self, 'crypt_bookmarks'):
            self.crypt_bookmarks.clear()
            self.crypt_bookmark_selector.items = []
        if hasattr(self, 'crypt_title'):
            self.crypt_title.text = private_label('Encrypted copy closed')
        if hasattr(self, 'crypt_password'):
            self.crypt_password.value = ''
        return True

    def clear_private_catalog(self):
        vault = getattr(self, 'vault_browser', None)
        if vault is not None and vault.provider.private:
            vault.dispose()
        self.hub_crypt_locations = []
        self.hub_crypt_roots = {}
        if hasattr(self, 'remote_item_view'):
            self.remote_item_password.value = ''
            for child in list(self.remote_item_view.children):
                self.remote_item_view.remove(child)
            self.remote_item_view.add(toga.Label('Connection closed. Browse the remote again.'))
        if hasattr(self, 'readers'):
            self.readers.catalog.clear_private_libraries()
        for drawer in getattr(self.adaptive, 'browsers', {}).values():
            drawer.generation += 1
            drawer.scoped_provider = None
            if drawer.provider is not None and drawer.provider.private:
                drawer.provider = None
                drawer.browser.stop()
                drawer.status.text = 'Private folders locked. Choose an available location.'
            if drawer.destination == 'documents':
                drawer.refresh_menu()
        self.editor_picker().clear()
        for name in ('file_browser', 'remote_browser'):
            browser = getattr(self, name, None)
            if browser is not None:
                browser.stop()
        if hasattr(self, 'files_view'):
            self.file_rows = {}
            self.file_roots = {}
            self.file_storage.items = self.file_destination.items = []
            self.file_provider = None
            self.file_selection.items = []
            self.file_name.value = self.file_target.value = self.file_location.value = ''
            self.file_status.value = ''
        self.crypt_labels = {}
        self.crypt_selector.items = []



    async def open_crypt(self, widget=None, *, copies=None, key=None, prepared=None, independent=False, edit=False, **kwargs):
        copies = copies or self.crypt_copies
        key = key if key is not None else self.crypt_labels.get(self.crypt_selector.value)
        if (self.cloud_busy and not (independent and self.transfer_busy and getattr(copies, 'offline', False))) or key is None:
            return
        password = self.crypt_password.value
        self.crypt_password.value = ''
        if self._crypt_cancel is not None:
            return
        if prepared is None and self.private_dirty():
            self.crypt_title.text = private_label('Unsaved changes: save, or discard and close.')
            self.resume_crypt()
            return
        if not independent:
            self.set_cloud_busy(True)
        self._crypt_cancel = threading.Event()
        reader = None
        try:
            if prepared is None:
                reader = await asyncio.to_thread(copies.open, key, password=password, cancelled=self._crypt_cancel.is_set)
                self._provider_comic_mode = self.private_comic_mode()
                kind, content = await asyncio.to_thread(self.provider_page_content, reader, 0)
            else:
                reader, kind, content = prepared
            initial_preview = None
            initial_preview_error = None
            if (not edit and reader.editable and not getattr(reader, 'read_only', False)
                    and reader.kind in {'.md', '.markdown'}):
                from .preview import markdown_preview, reader_image_source
                try:
                    initial_preview = await asyncio.to_thread(markdown_preview, content,
                        int(self.preferences.values['font_size']), image_source=reader_image_source(copies, reader))
                except ValueError as error:
                    # Keep the established source fallback and error feedback.
                    initial_preview_error = str(error)
            check_cancelled(self._crypt_cancel.is_set)
            from types import SimpleNamespace
            view = SimpleNamespace()
            view.crypt_reader = reader
            view._crypt_reader_store = copies
            view.crypt_title = toga.Label(private_label(reader.name), style=Pack(font_size=18))
            view.crypt_page = toga.Selection(items=reader.labels, style=Pack(height=44))
            view.crypt_page.value = reader.labels[0]
            view.crypt_read_page = toga.Button('Read selected page', on_press=self.read_crypt_page, style=Pack(height=44))
            view.crypt_bookmarks = set()
            view.epub_session_bookmarks = set()
            view.crypt_bookmark_button = toga.Button('Bookmark', on_press=self.toggle_private_bookmark,
                                                    enabled=not reader.editable, style=Pack(height=44))
            view.crypt_bookmark_selector = toga.Selection(items=['Bookmarks…'],
                on_change=self.select_private_bookmark, enabled=not reader.editable, style=Pack(height=44))
            from commonUtils.ui.native.code_input import CodeInput
            view.crypt_text = CodeInput(loop=self.loop, filename=reader.name, readonly=not reader.editable,
                highlighting=self.preferences.values.get('android_eink') != 'true',
                on_change=self.private_source_changed,
                style=Pack(flex=1, font_size=int(self.preferences.values['font_size'])))
            if getattr(reader, 'read_only', False):
                view.crypt_text.readonly = True
            from commonUtils.ui.native.image_canvas import ImageCanvas
            if reader.kind == '.pdf':
                from features.pdf.mobile.canvas import PDFCanvas
                view.crypt_image = PDFCanvas(on_page=self.swipe_crypt_page,
                    on_toggle=self.toggle_private_reading_mode, style=Pack(flex=1))
            else:
                view.crypt_image = ImageCanvas(on_page=self.swipe_crypt_page,
                    page_swipes_at_edges=reader.kind in {'.cbz', '.zip'},
                    on_toggle=self.toggle_private_reading_mode, style=Pack(flex=1))
            from .magnifier import bind
            bind(self, view.crypt_image)
            view.crypt_content = toga.Box(style=Pack(direction=COLUMN, flex=1))
            self._show_crypt_content(kind, content, view=view)
            view.crypt_save = toga.Button('Save encrypted copy' if getattr(copies, 'encrypted', True) else 'Save local file', on_press=self.save_crypt, enabled=reader.editable and not getattr(reader, 'read_only', False), style=Pack(height=44))
            view.crypt_read_page.enabled = not reader.editable
            read_only = getattr(reader, 'read_only', False)
            mutation_controls = [] if read_only else ([view.crypt_save,
                toga.Button('Save As…', on_press=self.show_crypt_save_as, style=Pack(height=44))]
                if reader.editable else [toga.Button('Edit metadata…', on_press=self.edit_crypt_metadata, style=Pack(height=44))])
            view.crypt_view = toga.Box(children=[view.crypt_title, view.crypt_page, view.crypt_read_page, view.crypt_content,
                *mutation_controls,
                toga.Button('Open…', on_press=self.show_editor_open, style=Pack(height=44)),
                toga.Label(private_label('Remote preview · Read-only' if read_only else
                    ('Edits stay in memory until saved to the selected local file.' if reader.editable else 'Reading position stays in this session'))),
                toga.Button('Cancel request', on_press=self.cancel_cloud, style=Pack(height=44)),
                *([] if read_only or not reader.editable else [toga.Button('Discard changes and close', on_press=self.discard_crypt, style=Pack(height=44))]),
                toga.Button('Close private reader', on_press=self.close_crypt, style=Pack(height=44))],
                style=Pack(direction=COLUMN, flex=1, margin=12))
            self.compact_private_view(view)
            if password:
                from features.rclone.mobile.session_privacy import ResumePassword
                view.privacy_gate = ResumePassword(password)
            elif getattr(self, 'privacy_gate', None) is not None:
                view.privacy_gate = self.privacy_gate
            handoff = (prepared is not None and getattr(self, 'save_as_source_document', None) is self.current
                       and getattr(self.current, 'private', False))
            if not self.show_view(view.crypt_view, checkpoint=not handoff, destination='documents', title=reader.name):
                return False
            self._crypt_cancel = None
            self.clear_private_reader(discard=True)
            self.__dict__.update(vars(view))
            if reader.editable and not getattr(reader, 'read_only', False) and reader.kind in {'.md', '.markdown'}:
                if edit:
                    self.show_private_markdown_editor()
                elif initial_preview_error is not None:
                    self.crypt_title.text = private_label(initial_preview_error)
                else:
                    self.toggle_private_preview(initial=True, rendered=initial_preview)
            privacy = getattr(getattr(self, 'app', self), 'screen_privacy', None)
            if privacy is not None:
                privacy.refresh()
            self.watch_provider_layout()
            self.watch_provider_epub_width()
            if view.crypt_reader.kind in {'.cbz', '.zip'}:
                await self.refresh_provider_comic_neighbors()
            return True
        except Exception as error:
            if self._crypt_cancel is not None and self._crypt_cancel.is_set():
                self.cloud_status.value = 'Remote opening cancelled.' if getattr(copies, 'remote_storage', False) else 'Private reading cancelled.'
                return False
            self.cloud_status.value = 'Private reading failed: ' + str(error)[:300]
            if getattr(copies, 'remote_storage', False):
                from commonUtils.archives.zip_access import ArchivePasswordError
                if isinstance(error, ArchivePasswordError):
                    row = next((row for row in self.app.cloud_rows.values() if row['path'] == key),
                               dict(path=key, directory=False, size=0))
                    self.app.show_remote_item_actions(row, password_required=True)
                    return False
                from features.rclone.remote_policy import LOCAL_COPY_MESSAGE
                await self.main_window.dialog(toga.InfoDialog('Remote preview unavailable',
                    str(error)[:200] + '\n\n' + LOCAL_COPY_MESSAGE))
        finally:
            if (prepared is None and getattr(copies, 'remote_storage', False) and reader is not None
                    and getattr(self, 'crypt_reader', None) is not reader):
                reader.source.close()
            password = None
            self._crypt_cancel = None
            if not independent:
                self.set_cloud_busy(False)

    def edit_crypt_metadata(self, widget=None, **kwargs):
        if getattr(self.crypt_reader, 'read_only', False):
            return
        if self.cloud_busy or self.crypt_reader is None or self.crypt_reader.editable:
            return
        if self.crypt_metadata_fields:
            self.show_view(self.crypt_metadata_view)
            return
        reader = self.crypt_reader
        if reader.kind == '.epub':
            from features.books.mobile.metadata import values
            initial, self.crypt_metadata_values = values(reader.book)
        else:
            try:
                from features.comics.mobile.metadata import values
                initial = values(reader.comic)
            except Exception as error:
                self.crypt_title.text = private_label('Cannot edit metadata: ' + str(error)[:200])
                return
        self.crypt_metadata_initial = initial
        self.crypt_metadata_fields = {key: toga.MultilineTextInput(value=value, style=Pack(height=80)) for key, value in initial.items()}
        self.crypt_metadata_status = toga.Label(private_label('Save updates only the encrypted local copy.'))
        children = [toga.Label(private_label('Edit metadata: ' + reader.name)), self.crypt_metadata_status]
        for key, field in self.crypt_metadata_fields.items():
            children.extend([toga.Label(key), field])
        self.crypt_metadata_save = toga.Button('Save encrypted metadata', on_press=self.save_crypt_metadata, style=Pack(height=44))
        children.extend([self.crypt_metadata_save,
            toga.Button('Cancel request', on_press=self.cancel_cloud, style=Pack(height=44)),
            toga.Button('Back to reader', on_press=self.resume_crypt, style=Pack(height=44)),
            toga.Button('Discard changes and close', on_press=self.discard_crypt, style=Pack(height=44))])
        self.crypt_metadata_view = toga.ScrollContainer(horizontal=False, content=toga.Box(children=children, style=Pack(direction=COLUMN, margin=12)), style=Pack(flex=1))
        self.show_view(self.crypt_metadata_view)

    async def save_crypt_metadata(self, widget=None, **kwargs):
        if getattr(self.crypt_reader, 'read_only', False):
            return
        if self.cloud_busy or self.crypt_reader is None:
            return
        edited = {key: field.value for key, field in self.crypt_metadata_fields.items()}
        if self.crypt_reader.kind == '.epub':
            from features.books.mobile.metadata import patch
            changes = patch(self.crypt_metadata_initial, edited, self.crypt_metadata_values)
        else:
            from features.comics.mobile.metadata import patch
            changes = patch(self.crypt_metadata_initial, edited)
        if not changes:
            self.crypt_metadata_status.text = 'No changes to save.'
            return
        self.set_cloud_busy(True)
        self._crypt_cancel = threading.Event()
        self.crypt_metadata_save.enabled = False
        for field in self.crypt_metadata_fields.values():
            field.readonly = True
        try:
            self.crypt_reader = await asyncio.to_thread(self._crypt_reader_store.save_metadata, self.crypt_reader, changes, cancelled=self._crypt_cancel.is_set)
            if self.crypt_reader.kind == '.epub':
                self.crypt_metadata_values = {key: self.crypt_reader.book.values(key) for key in self.crypt_metadata_fields}
                saved = {key: '\n'.join(value) if key in {'creator', 'subject'} else next(iter(value), '')
                         for key, value in self.crypt_metadata_values.items()}
            else:
                saved = {key: self.crypt_reader.comic.info.get_field(key) for key in self.crypt_metadata_fields}
            for key, field in self.crypt_metadata_fields.items():
                field.value = saved[key]
            self.crypt_metadata_initial = saved
            self.crypt_metadata_status.text = 'Metadata saved encrypted locally.'
            index = min(self.crypt_reader.labels.index(self.crypt_page.value)
                        if self.crypt_page.value in self.crypt_reader.labels else 0, len(self.crypt_reader.labels) - 1)
            self.crypt_page.items = self.crypt_reader.labels
            self.crypt_page.value = self.crypt_reader.labels[index]
            self._provider_comic_mode = self.private_comic_mode()
            kind, content = await asyncio.to_thread(self.provider_page_content, self.crypt_reader, index)
            self._show_crypt_content(kind, content)
            self.refresh_private_bookmarks()
            self.watch_provider_layout()
            self.watch_provider_epub_width()
        except Exception as error:
            self.crypt_metadata_status.text = private_label('Save failed; edits retained: ' + str(error)[:200])
        finally:
            self._crypt_cancel = None
            self.crypt_metadata_save.enabled = True
            for field in self.crypt_metadata_fields.values():
                field.readonly = False
            self.set_cloud_busy(False)

    async def save_crypt(self, widget=None, **kwargs):
        if getattr(self.crypt_reader, 'read_only', False):
            return
        if self.cloud_busy or self.crypt_reader is None or not self.crypt_reader.editable:
            return
        self.set_cloud_busy(True)
        self.crypt_save.enabled = False
        self.crypt_text.readonly = True
        self._crypt_cancel = threading.Event()
        try:
            self.crypt_reader = await asyncio.to_thread(self._crypt_reader_store.save, self.crypt_reader, self.crypt_text.value, cancelled=self._crypt_cancel.is_set)
            self.crypt_title.text = private_label(self.crypt_reader.name + (' · Saved encrypted locally' if getattr(self._crypt_reader_store, 'encrypted', True) else ' · Saved locally'))
        except Exception as error:
            self.crypt_title.text = private_label('Save failed; edits retained: ' + str(error)[:200])
        finally:
            self._crypt_cancel = None
            self.crypt_text.readonly = False
            self.crypt_save.enabled = True
            self.set_cloud_busy(False)
            self.refresh_private_text_controls()

    def discard_crypt(self, widget=None, **kwargs):
        if not self.cloud_busy and self.clear_private_reader(discard=True):
            self.show_cloud()

    def _show_crypt_content(self, kind, content, *, view=None, owner=None):
        controller = owner or self
        view = self if view is None else view
        prepared_spread = None
        if view.crypt_reader.book is None and kind == 'spread':
            from features.comics.mobile.presentation import SpreadView
            from commonUtils.ui.native.image_canvas import ImageCanvas
            indices, data = content
            # Decode/compose before retiring the displayed private pixels. Native
            # allocation or decoder failures must preserve the previous spread.
            prepared_spread = SpreadView(data, canvas=ImageCanvas,
                on_page=controller.swipe_crypt_page, on_toggle=controller.toggle_private_reading_mode,
                right_to_left=getattr(view.crypt_reader, 'right_to_left', False),
                viewport=controller.private_comic_viewport(view),
                seam=controller.private_comic_seam(view))
            from .magnifier import bind
            bind(controller, prepared_spread)
        from .page_animation import page_direction, begin_page_slide, finish_page_slide
        index = view.crypt_reader.labels.index(view.crypt_page.value)
        direction = 0
        if (kind in {'spread', 'image'} and view.crypt_reader.kind in {'.cbz', '.zip'}
                and view.crypt_content.children):
            direction = page_direction(getattr(view, '_provider_displayed_index', None), index,
                right_to_left=getattr(view.crypt_reader, 'right_to_left', False))
        begin_page_slide(view.crypt_content, direction, self.preferences.values)
        for child in list(view.crypt_content.children):
            if hasattr(child, 'dispose') and child not in (view.crypt_image, view.crypt_text):
                child.dispose()
            view.crypt_content.remove(child)
        view.crypt_text.value = ''
        view.crypt_image.image = None
        if hasattr(view, 'provider_epub_view'):
            view.provider_epub_view.dispose()
            del view.provider_epub_view
        if view.crypt_reader.book is not None:
            from features.books.mobile.provider_reader import provider_view
            from features.books.mobile.typography import options as typography_options
            book = view.crypt_reader.book
            index = view.crypt_reader.labels.index(view.crypt_page.value)
            locations = getattr(view, '_provider_epub_locations', {})
            view._provider_epub_locations = locations
            target = getattr(controller, '_provider_epub_target', None)
            controller._provider_epub_target = None
            offset = locations.get(book.spine[index], 0)
            if target is not None:
                from features.books.locations import ChapterText
                from features.books.mobile.content import chapter_html
                offset = ChapterText(chapter_html(book, index)).anchors.get(target, 0) if isinstance(target, str) else target
            view.provider_epub_view = provider_view(book, index, offset=offset,
                font_size=int(self.preferences.values['font_size']),
                margin=int(self.preferences.values['reading_margin']), theme=self.preferences.values['reading_theme'], typography=typography_options(self.preferences.values),
                on_chapter=controller.open_provider_epub_chapter,
                on_position=lambda value: locations.update({book.spine[index]: value}))
            chapters = getattr(view.provider_epub_view, 'chapters', None)
            if chapters is not None:
                from .appearance import hierarchy_row_style
                chapters.row_style, chapters.current = hierarchy_row_style, index
                chapters.render()
            tools = view.provider_epub_view.tools
            if tools.button in tools.widget.children:
                tools.widget.remove(tools.button)
            for control in (view.crypt_bookmark_button, view.crypt_bookmark_selector):
                if control.parent is not None:
                    control.parent.remove(control)
                tools.panel.add(control)
            tools.panel.add(toga.Label('Bookmarks stay in this session and are cleared on close.'))
            view.crypt_content.add(view.provider_epub_view)
        elif kind == 'spread':
            view.provider_spread = prepared_spread
            view.crypt_content.add(prepared_spread)
            view.crypt_reader.comic_navigation.visible = indices
        elif kind == 'image':
            view.crypt_image.image = toga.Image(src=content)
            view.crypt_content.add(view.crypt_image)
        else:
            view.crypt_text.value = content
            view.crypt_content.add(view.crypt_text)
        finish_page_slide(view.crypt_content, direction, self.preferences.values)
        comic = view.crypt_reader.kind in {'.cbz', '.zip'}
        for child in view.crypt_content.children:
            if hasattr(child, 'magnifier_enabled'):
                child.magnifier_enabled = (comic or view.crypt_reader.kind == '.pdf') and getattr(view, 'crypt_immersive', False)
        view._provider_displayed_index = view.crypt_reader.labels.index(view.crypt_page.value)
        if view.crypt_reader.kind == '.pdf' and hasattr(view, 'pdf_number'):
            view.pdf_number.value = str(view._provider_displayed_index + 1)

    async def read_crypt_page(self, widget=None, **kwargs):
        if self.cloud_busy or self.crypt_reader is None or self.crypt_reader.editable:
            return
        panel = getattr(self, 'provider_epub_view', None)
        if panel is not None and hasattr(panel, 'close_read_aloud'):
            panel.close_read_aloud()
        self.set_cloud_busy(True)
        self.crypt_read_page.enabled = False
        try:
            index = self.crypt_reader.labels.index(self.crypt_page.value)
            self._provider_viewport = self.private_comic_viewport()
            self._provider_comic_mode = self.private_comic_mode()
            reader = self.crypt_reader
            token = self.workspace.token(self.session.id)
            kind, content = await asyncio.to_thread(self.provider_page_content, reader, index)
            if (not self.active_host or self.crypt_reader is not reader
                    or not self.workspace.accepts(token) or self.manager.active is not self):
                return
            self._show_crypt_content(kind, content)
            self.page_suspended = False
            if reader.kind in {'.pdf', '.cbz', '.zip'}:
                self.crypt_title.text = private_label(f'{reader.name} · {index + 1}/{len(reader.labels)}')
            self.refresh_private_bookmarks()
            self.watch_provider_layout()
            self.watch_provider_epub_width()
            self.page_footer.sync(comic=reader.kind in {'.cbz', '.zip'}, count=len(reader.labels),
                                  index=index, right_to_left=getattr(reader, 'right_to_left', False))
            self.previous_page.enabled = reader.book is not None or index > 0
            self.next_page.enabled = reader.book is not None or (reader.comic_navigation.next(index) is not None if hasattr(reader, 'comic_navigation') else index + 1 < len(reader.labels))
        except Exception as error:
            self.crypt_title.text = private_label('Cannot read page: ' + str(error)[:200])
            if self.crypt_reader is not None:
                self.crypt_page.value = self.crypt_reader.labels[getattr(self, '_provider_displayed_index', 0)]
        finally:
            self.crypt_read_page.enabled = True
            self.set_cloud_busy(False)

    def refresh_private_bookmarks(self):
        index = self.crypt_reader.labels.index(self.crypt_page.value)
        self.crypt_bookmark_selector.on_change = None
        self.provider_bookmark_choices = {}
        if self.crypt_reader.book is not None:
            for chapter, offset in sorted(getattr(self, 'epub_session_bookmarks', set())):
                label = f'{self.crypt_reader.labels[chapter]} · text {offset}'
                self.provider_bookmark_choices[label] = (chapter, offset)
        self.crypt_bookmark_selector.items = ['Bookmarks…',
            *(self.crypt_reader.labels[i] for i in sorted(self.crypt_bookmarks)),
            *self.provider_bookmark_choices]
        self.crypt_bookmark_selector.value = 'Bookmarks…'
        self.crypt_bookmark_selector.on_change = self.select_private_bookmark
        marked = ((index, self.provider_epub_view.offset) in getattr(self, 'epub_session_bookmarks', set())) if self.crypt_reader.book is not None else index in self.crypt_bookmarks
        self.crypt_bookmark_button.text = 'Unbookmark' if marked else 'Bookmark'

    def toggle_private_bookmark(self, widget=None, **kwargs):
        if self.cloud_busy or self.crypt_reader is None or self.crypt_reader.editable:
            return
        index = self.crypt_reader.labels.index(self.crypt_page.value)
        if self.crypt_reader.book is not None:
            offset = self.provider_epub_view.offset
            value = (index, offset)
            if value in self.epub_session_bookmarks:
                self.epub_session_bookmarks.remove(value)
            elif len(self.epub_session_bookmarks) < 200:
                self.epub_session_bookmarks.add(value)
            self.refresh_private_bookmarks()
            return
        if index in self.crypt_bookmarks:
            self.crypt_bookmarks.remove(index)
        elif len(self.crypt_bookmarks) < 200:
            self.crypt_bookmarks.add(index)
        self.refresh_private_bookmarks()

    def select_private_bookmark(self, widget=None, **kwargs):
        if self.cloud_busy or self.crypt_reader is None:
            return
        try:
            label = self.crypt_bookmark_selector.value
        except IndexError:
            return
        if label in getattr(self, 'provider_bookmark_choices', {}):
            chapter, offset = self.provider_bookmark_choices[label]
            self._provider_epub_target = offset
            self.loop.create_task(self.move_private_page(chapter))
        elif label in self.crypt_reader.labels:
            self.crypt_page.value = label
            self.loop.create_task(self.read_crypt_page())

    def swipe_crypt_page(self, direction):
        if self.crypt_reader is None or self.crypt_reader.editable:
            return
        if hasattr(self.crypt_reader, 'comic_navigation'):
            schedule_swipe(self, direction, right_to_left=getattr(self.crypt_reader, 'right_to_left', False),
                           busy=self.cloud_busy, move=self.move_provider_comic)
            return
        schedule_swipe(self, direction, position=self.crypt_reader.labels.index(self.crypt_page.value),
                       count=len(self.crypt_reader.labels), right_to_left=getattr(self.crypt_reader, 'right_to_left', False),
                       busy=self.cloud_busy, move=self.move_private_page)

    async def move_private_page(self, index):
        if self.cloud_busy or self.crypt_reader is None or not 0 <= index < len(self.crypt_reader.labels):
            return
        self.crypt_page.value = self.crypt_reader.labels[index]
        await self.read_crypt_page()

    async def previous_private_page(self, widget=None, **kwargs):
        if self.crypt_reader is not None and hasattr(self.crypt_reader, 'comic_navigation'):
            await self.move_provider_comic(-1)
            return
        if hasattr(self, 'provider_epub_view') and self.provider_epub_view.turn(-1):
            return
        if self.crypt_reader is not None:
            await self.move_private_page(self.crypt_reader.labels.index(self.crypt_page.value) - 1)

    async def next_private_page(self, widget=None, **kwargs):
        if self.crypt_reader is not None and hasattr(self.crypt_reader, 'comic_navigation'):
            await self.move_provider_comic(1)
            return
        if hasattr(self, 'provider_epub_view') and self.provider_epub_view.turn(1):
            return
        if self.crypt_reader is not None:
            await self.move_private_page(self.crypt_reader.labels.index(self.crypt_page.value) + 1)

    def compact_private_view(self, view):
        from .action_menu import FeatureCommands
        from .reader_controls import ComicHeader, comic_actions, comic_pages
        old = view.crypt_view
        comic = view.crypt_reader.kind in {'.cbz', '.zip'}
        view.crypt_actions = icon_button('more', 'Reader actions' if comic else 'Private document actions')
        for control in (view.crypt_title, view.crypt_page, view.crypt_read_page, view.crypt_content, view.crypt_save):
            if control in old.children:
                old.remove(control)
        view.crypt_tools_view = toga.ScrollContainer(horizontal=False, content=old, style=Pack(flex=1))
        old.add(toga.Button('Return to private document', on_press=self.resume_crypt, style=Pack(height=44)))
        if view.crypt_reader.book is not None:
            old.insert(0, toga.Button('Contents and bookmarks', on_press=self.show_provider_epub_navigation,
                                     style=Pack(height=44)))
        if comic:
            host = getattr(self, 'app', self)
            writable = not getattr(view.crypt_reader, 'read_only', False)
            neighbors = writable and getattr(view._crypt_reader_store, 'provider', None) is not None
            actions = comic_actions(pages=self.show_private_tools, appearance=self.show_provider_layout,
                reading_mode=self.toggle_private_reading_mode, fit=self.fit_private_page,
                metadata=self.edit_crypt_metadata if writable else None, info=self.show_provider_comic_info,
                close=self.close_crypt)
            view.crypt_tools_view = comic_pages(view.crypt_page, self.resume_crypt)
        elif getattr(view.crypt_reader, 'read_only', False):
            actions = [('Reader tools…', self.show_private_tools)]
            if view.crypt_reader.book is not None:
                actions.extend([('Read aloud…', self.show_provider_read_aloud), ('Find in chapter…', self.show_provider_epub_find),
                    ('Appearance…', self.show_provider_layout)])
            elif getattr(view.crypt_reader, 'image_document', False):
                actions.append(('Fit image', self.fit_private_page))
            actions.append(('Close private document', self.close_crypt))
        else:
            actions = [('Open / Save As…' if view.crypt_reader.editable else 'Open / Metadata…', self.show_private_tools)]
            if view.crypt_reader.book is not None:
                actions.extend([('Read aloud…', self.show_provider_read_aloud), ('Find in chapter…', self.show_provider_epub_find),
                    ('Appearance…', self.show_provider_layout)])
            actions.append(('Close private document', self.close_crypt))
        if view.crypt_reader.book is not None or view.crypt_reader.kind == '.pdf':
            actions.append(('Fullscreen', self.toggle_private_reading_mode))
        if view.crypt_reader.book is not None or view.crypt_reader.kind in {'.md', '.markdown'}:
            app = getattr(self, 'app', self)
            actions.append(('Open beside another document', app.adaptive.show_pair_picker))
        view.crypt_actions_menu = FeatureCommands(view.crypt_actions, self, actions, self.show_private_tools)
        view.crypt_title.style.flex = 1
        view.crypt_page.style.flex = 1
        view.crypt_title.style.font_size = 12
        controls = [toga.Box(children=[view.crypt_title, view.crypt_actions], style=Pack(direction=ROW))]
        view.reader_toolbar = controls[0]
        if view.crypt_reader.book is not None:
            view.reader_speech_button = icon_button('speaker', 'Read aloud', on_press=self.show_provider_read_aloud)
            view.reader_toolbar.insert(1, view.reader_speech_button)
        if view.crypt_reader.kind == '.pdf':
            async def jump(widget=None, **kwargs):
                from features.pdf.document import page_index
                try:
                    index = page_index(view.pdf_number.value, len(view.crypt_reader.labels))
                except ValueError as error:
                    view.crypt_title.text = private_label(error)
                    return
                await self.move_private_page(index)
            view.pdf_number = toga.TextInput(value='1', on_confirm=jump, style=Pack(flex=1, height=44))
            jump_row = toga.Box(children=[toga.Label(f'Page / {len(view.crypt_reader.labels)}'),
                view.pdf_number, toga.Button('Go', on_press=jump, style=Pack(height=44))], style=Pack(direction=ROW))
            from features.pdf.mobile.search import PDFSearchBar
            reader = view.crypt_reader
            view.pdf_search = PDFSearchBar(reader.pdf, on_page=self.move_private_page,
                alive=lambda: self.active_host and self.crypt_reader is reader
                    and self.session.id in self.workspace.sessions and self.manager.active is self)
            from features.pdf.mobile.canvas import PDFTools
            from features.pdf.mobile.contents import PDFContents
            from .appearance import hierarchy_row_style
            view.pdf_contents = PDFContents(reader.pdf, on_page=self.move_private_page,
                alive=lambda: self.active_host and self.crypt_reader is reader
                    and self.session.id in self.workspace.sessions and self.manager.active is self,
                row_style=hierarchy_row_style)
            view.pdf_tools = PDFTools([jump_row, view.pdf_contents, view.pdf_search])
            controls.append(view.pdf_tools.widget)
        elif not view.crypt_reader.editable and not comic and view.crypt_reader.book is None:
            controls.append(toga.Box(children=[view.crypt_page, view.crypt_read_page], style=Pack(direction=ROW)))
        controls.append(view.crypt_content)
        if view.crypt_reader.editable:
            view.crypt_save.text = 'Save'
            footer = toga.Box(children=[] if getattr(view.crypt_reader, 'read_only', False) else [view.crypt_save],
                              style=Pack(direction=ROW, margin_top=4))
            view.crypt_save.style.flex = 1
            if view.crypt_reader.kind in {'.md', '.markdown'}:
                from .control_icons import apply_icon
                apply_icon(view.crypt_save, 'save', 'Save Markdown')
                if view.crypt_save in footer.children:
                    footer.remove(view.crypt_save)
                view.crypt_preview_button = icon_button('view', 'View Markdown', on_press=self.toggle_private_preview)
                view.reader_toolbar.insert(len(view.reader_toolbar.children) - 1, view.crypt_preview_button)
                if not getattr(view.crypt_reader, 'read_only', False):
                    view.crypt_edit_mode = toga.Selection(items=['Formatted', 'Source'],
                        on_change=self.private_edit_mode_changed, style=Pack(flex=1, height=44))
                    footer.add(view.crypt_edit_mode)
                view.crypt_markdown_footer = footer
            if footer.children:
                controls.append(footer)
        if not view.crypt_reader.editable:
            from .workspace_navigation import menu_button
            host = getattr(self, 'app', self)
            reader_menu = (menu_button(self.toggle_provider_epub_tools, label='Contents and bookmarks')
                           if view.crypt_reader.book is not None else menu_button(lambda widget, **kw:
                               host.adaptive.show_browser(getattr(view, 'presentation_destination', 'documents'))))
            controls[0].insert(0, reader_menu)
            if comic:
                controls[0].remove(reader_menu)
                controls[0].remove(view.crypt_actions)
                controls[0].remove(view.crypt_title)
                view.comic_header = ComicHeader(reader_menu, view.crypt_actions,
                    previous=self.previous_provider_comic_file if neighbors else None,
                    following=self.next_provider_comic_file if neighbors else None)
                header = view.comic_header.widget
            else:
                header = toga.Box(children=controls[:-1], style=Pack(direction=COLUMN))
            view.previous_page, view.next_page = page_buttons(self.previous_private_page, self.next_private_page)
            view.page_footer = PageFooter(view.previous_page, view.next_page, self.move_private_page,
                compact=view.crypt_reader.book is not None)
            view.page_footer.sync(comic=view.crypt_reader.kind in {'.cbz', '.zip'},
                                  count=len(view.crypt_reader.labels), index=0,
                                  right_to_left=getattr(view.crypt_reader, 'right_to_left', False))
            footer = view.page_footer.widget
            if view.crypt_reader.book is not None:
                view.reader_toolbar.insert(1, footer)
                view.crypt_title.style.update(flex=1, width=1, height=48, margin=0)
            view.reader_restore = (toga.Button('Show reading controls', on_press=self.toggle_private_reading_mode,
                                             style=Pack(height=48)) if view.crypt_reader.book is not None or view.crypt_reader.kind == '.pdf' else None)
            view.reading_frame = ReadingFrame(view.crypt_content,
                [header, footer, view.crypt_title] if comic else
                [header] if view.crypt_reader.book is not None else [header, footer],
                margin=0 if view.crypt_reader.book is not None else 16, restore=view.reader_restore)
            view.crypt_view = view.reading_frame.widget
            if view.crypt_reader.book is not None:
                view.crypt_view._native_reader_toolbar = header
                view.crypt_view._native_reader_status = view.crypt_title
                view.crypt_view._native_reader_buttons = lambda: [view.previous_page, view.next_page,
                    view.reader_speech_button, view.crypt_actions]
            view.crypt_view._workspace_menu_button = reader_menu
            view.crypt_controls = view.reading_frame.controls
            view.previous_page.enabled = False
            view.next_page.enabled = view.crypt_reader.book is not None or len(view.crypt_reader.labels) > 1
        else:
            markdown = view.crypt_reader.kind in {'.md', '.markdown'}
            view.crypt_view = toga.Box(children=controls, style=Pack(direction=COLUMN, margin=0 if markdown else 12, flex=1))
            if markdown:
                view.crypt_view._workspace_toolbar = view.reader_toolbar
                view._native_reading_buttons = [view.crypt_preview_button, view.crypt_actions]
                view.crypt_view._native_reader_toolbar = view.reader_toolbar
                view.crypt_view._native_reader_status = view.crypt_title
                view.crypt_view._native_reader_buttons = lambda: view._native_reading_buttons
                view.crypt_title.style.update(flex=1, width=1, height=48, margin=0)
                self.refresh_private_text_controls(view=view)
            view.crypt_controls = [control for control in controls if control is not view.crypt_content]
        view.crypt_immersive = view.crypt_reader.kind in {'.cbz', '.zip'}
        if view.crypt_immersive:
            view.reading_frame.set_immersive(True, comic=True)
        self.register_transfer_status(view.crypt_view)

    def toggle_private_reading_mode(self, widget=None, **kwargs):
        if self.crypt_reader is None or (self.crypt_reader.kind not in {'.cbz', '.zip'}
                                        and self.crypt_reader.book is None and self.crypt_reader.kind != '.pdf'):
            return
        self.crypt_immersive = not self.crypt_immersive
        panel = getattr(self, 'provider_epub_view', None)
        if panel is not None:
            panel.tools.close()
        pdf_tools = getattr(self, 'pdf_tools', None)
        if pdf_tools is not None:
            pdf_tools.close()
        comic = self.crypt_reader.kind in {'.cbz', '.zip'}
        self.reading_frame.set_immersive(self.crypt_immersive, comic=comic, image=self.crypt_reader.kind == '.pdf')
        self.refresh_transfer_status()
        self.resume_crypt()

    def clear_private_preview(self):
        footer = getattr(self, 'crypt_markdown_footer', None)
        mode = getattr(self, 'crypt_edit_mode', None)
        if footer is not None and mode is not None and mode not in footer.children:
            footer.add(mode)
        speech = getattr(self, "markdown_speech", None)
        if speech is not None:
            speech.close()
            toolbar = getattr(self, 'reader_toolbar', None)
            if toolbar is not None and speech.button in toolbar.children:
                toolbar.remove(speech.button)
        formatted = getattr(self, 'crypt_formatted', None)
        if formatted is not None:
            formatted.dispose()
            if formatted.view in self.crypt_content.children:
                self.crypt_content.remove(formatted.view)
            self.crypt_formatted = None
            if self.crypt_text not in self.crypt_content.children:
                self.crypt_content.add(self.crypt_text)
        pending = getattr(self, '_private_preview_pending', None)
        if pending is not None:
            pending.cancel()
            self._private_preview_pending = None
        preview = getattr(self, 'crypt_preview', None)
        if preview is not None:
            native = getattr(preview._impl, 'native', None)
            if native is not None:
                native.stopLoading()
            preview.set_content('https://logistics.invalid/closed/', '<p>Preview closed.</p>')
            if preview in self.crypt_content.children:
                self.crypt_content.remove(preview)
                if self.crypt_text not in self.crypt_content.children:
                    self.crypt_content.add(self.crypt_text)
            from .control_icons import apply_icon
            apply_icon(self.crypt_preview_button, 'view', 'View Markdown')
        self.refresh_private_text_controls()

    def refresh_private_text_controls(self, *, view=None):
        owner = view or self
        reader = getattr(owner, 'crypt_reader', None)
        toolbar = getattr(owner, 'reader_toolbar', None)
        if reader is None or toolbar is None or reader.kind not in {'.md', '.markdown'}:
            return
        dirty = owner.crypt_text.value != reader.text and not getattr(reader, 'read_only', False)
        owner.crypt_save.enabled = dirty and not self.cloud_busy
        native_toolbar = type(toolbar._impl).__module__.startswith('toga_iOS.')
        if dirty and not native_toolbar and owner.crypt_save not in toolbar.children:
            toolbar.insert(len(toolbar.children) - 1, owner.crypt_save)
        elif not dirty and owner.crypt_save in toolbar.children:
            toolbar.remove(owner.crypt_save)
        footer = getattr(owner, 'crypt_markdown_footer', None)
        if footer is not None:
            # A hidden source-mode selector must not leave a blank footer row.
            footer.style.margin_top = 0
            if footer.children:
                del footer.style.height
            else:
                footer.style.height = 0
        buttons = getattr(owner, '_native_reading_buttons', None)
        if buttons is not None:
            buttons[:] = ([owner.crypt_save] if dirty else []) + [owner.crypt_preview_button]
            speech = getattr(owner, 'markdown_speech', None)
            preview = getattr(owner, 'crypt_preview', None)
            if speech is not None and preview is not None and preview in owner.crypt_content.children:
                buttons.append(speech.button)
            buttons.append(owner.crypt_actions)
            app = getattr(self, 'app', self)
            body = app.routes.body()
            if owner.crypt_view in body.children:
                from .workspace_navigation import sync_reader_toolbar
                sync_reader_toolbar(app, owner.crypt_view)

    def private_source_changed(self, widget, **kwargs):
        if widget is not getattr(self, 'crypt_text', None):
            return
        self.refresh_private_text_controls()
        formatted = getattr(self, 'crypt_formatted', None)
        if formatted is not None and formatted.view in self.crypt_content.children:
            try:
                formatted.load(widget.value)
            except ValueError as error:
                self.crypt_title.text = private_label(str(error))
        speech = getattr(self, 'markdown_speech', None)
        if speech is not None:
            speech.close()
        preview = getattr(self, 'crypt_preview', None)
        if preview is None or preview not in self.crypt_content.children:
            return
        pending = getattr(self, '_private_preview_pending', None)
        if pending is not None:
            pending.cancel()
        reader = self.crypt_reader
        def render():
            self._private_preview_pending = None
            if self.crypt_reader is not reader or reader is None:
                return
            from .preview import markdown_preview, reader_image_source
            try:
                preview.set_content('https://logistics.invalid/live/',
                    markdown_preview(widget.value, int(self.preferences.values['font_size']),
                        image_source=reader_image_source(self._crypt_reader_store, reader)))
            except ValueError as error:
                self.crypt_title.text = private_label(str(error))
        self._private_preview_pending = self.loop.call_later(.25, render)

    def toggle_private_preview(self, widget=None, *, initial=False, rendered=None, **kwargs):
        if (not initial and self.cloud_busy and not getattr(self, 'transfer_busy', False)) or self.crypt_reader is None or not self.crypt_reader.editable:
            return
        preview = getattr(self, 'crypt_preview', None)
        if preview is not None and preview in self.crypt_content.children:
            self.crypt_markdown_mode = 'source'
            self.clear_private_preview()
            if not getattr(self.crypt_reader, 'read_only', False):
                self.show_private_markdown_editor()
            return
        from .preview import markdown_preview, reader_image_source
        from uuid import uuid4
        try:
            content = rendered if rendered is not None else markdown_preview(
                self.crypt_text.value, int(self.preferences.values['font_size']),
                image_source=reader_image_source(self._crypt_reader_store, self.crypt_reader))
        except ValueError as error:
            self.crypt_title.text = private_label(str(error))
            return
        if preview is None:
            self.crypt_preview = preview = toga.WebView(on_navigation_starting=lambda widget, url, **kw: False,
                                                       style=Pack(flex=1))
        preview.set_content('https://logistics.invalid/' + uuid4().hex + '/', content)
        self.crypt_markdown_mode = 'preview'
        footer = getattr(self, 'crypt_markdown_footer', None)
        mode = getattr(self, 'crypt_edit_mode', None)
        if footer is not None and mode is not None and mode in footer.children:
            footer.remove(mode)
        self.crypt_content.clear()
        self.crypt_content.add(preview)
        from .markdown_speech import MarkdownSpeech
        speech = getattr(self, "markdown_speech", None)
        if speech is None:
            self.markdown_speech = speech = MarkdownSpeech(getattr(self, "app", self), preview, self.crypt_content,
                privacy_gate=lambda: getattr(self, "privacy_gate", None), valid=lambda: speech_session_valid(self))
        speech.close()
        speech.web = preview
        if speech.button not in self.reader_toolbar.children:
            self.reader_toolbar.insert(len(self.reader_toolbar.children) - 1, speech.button)
        from .control_icons import apply_icon
        apply_icon(self.crypt_preview_button, 'view' if getattr(self.crypt_reader, 'read_only', False) else 'edit',
            'View source text' if getattr(self.crypt_reader, 'read_only', False) else 'Edit Markdown')
        self.refresh_private_text_controls()

    def private_edit_mode_changed(self, widget=None, **kwargs):
        if getattr(self, 'crypt_reader', None) is None:
            return
        if getattr(self.crypt_reader, 'read_only', False):
            return
        self.clear_private_preview()
        self.show_private_markdown_editor()

    def show_private_markdown_editor(self):
        if self.crypt_reader is None or getattr(self.crypt_reader, 'read_only', False):
            return
        self.crypt_markdown_mode = 'edit'
        if getattr(self.crypt_edit_mode, 'value', 'Formatted') == 'Source':
            return
        from features.text_editor.mobile.markdown_editor import FormattedMarkdownInput
        reader = self.crypt_reader
        def changed(text):
            if (self.crypt_reader is reader and reader is not None and self.active_host
                    and formatted.view in self.crypt_content.children):
                self.crypt_text.value = text
        from .preview import reader_image_source
        from .palette import css_variables
        formatted = FormattedMarkdownInput(changed, font_size=int(self.preferences.values['font_size']),
            stylesheet=css_variables(),
            image_source=lambda: reader_image_source(self._crypt_reader_store, reader))
        try:
            formatted.load(self.crypt_text.value)
        except ValueError as error:
            formatted.dispose()
            self.crypt_title.text = private_label(str(error))
            return
        self.crypt_formatted = formatted
        self.crypt_content.clear()
        self.crypt_content.add(formatted.view)

    def show_private_tools(self, widget=None, **kwargs):
        if not self.cloud_busy:
            title = 'Comic pages' if self.crypt_reader is not None and self.crypt_reader.kind in {'.cbz', '.zip'} else 'Private document actions'
            self.show_view(self.crypt_tools_view, destination='documents', route='private-tools', title=title)

    async def show_provider_comic_info(self, widget=None, **kwargs):
        if (self.crypt_reader is None or self.crypt_reader.kind not in {'.cbz', '.zip'}
                or not self.manager.available(self.session.id)):
            return
        from .reader_controls import provider_comic_path
        path = provider_comic_path(self._crypt_reader_store, self.crypt_reader)
        await self.main_window.dialog(toga.InfoDialog('Comic path', path))

    def fit_private_page(self, widget=None, **kwargs):
        view = getattr(self, 'provider_spread', self.crypt_image)
        view.fit_page()

    def close_crypt(self, widget=None, **kwargs):
        if not self.cloud_busy and self.clear_private_reader():
            self.show_cloud()


    def show_provider_epub_find(self, widget=None, **kwargs):
        panel = getattr(self, 'provider_epub_view', None)
        if panel is not None and not self.cloud_busy:
            if hasattr(panel, 'show_find'):
                panel.show_find()
            else:
                panel.tools.toggle()

    def toggle_provider_epub_tools(self, widget=None, **kwargs):
        panel = getattr(self, 'provider_epub_view', None)
        if not self.cloud_busy and panel is not None:
            panel.tools.toggle()

    async def show_provider_epub_navigation(self, widget=None, **kwargs):
        if self.cloud_busy or self.crypt_reader is None or self.crypt_reader.book is None:
            return
        if getattr(self, 'page_suspended', False):
            await self.read_crypt_page()
        self.resume_crypt()
        panel = getattr(self, 'provider_epub_view', None)
        if panel is not None and panel.tools.panel not in panel.tools.widget.children:
            panel.tools.toggle()

    def open_provider_epub_chapter(self, index, fragment=''):
        if self.cloud_busy or self.crypt_reader is None:
            return
        self._provider_epub_target = fragment
        self.loop.create_task(self.move_private_page(index))


    def provider_page_content(self, reader, index):
        if reader.kind == '.pdf' or reader.book is not None or reader.editable or getattr(reader, 'image_document', False):
            return reader.page(index)
        from features.comics.mobile.navigation import provider_navigation
        if not hasattr(reader, 'comic_navigation'):
            reader.comic_navigation = provider_navigation(reader)
        viewport = getattr(self, '_provider_viewport', (1, 1))
        return 'spread', reader.comic_navigation.load(index, viewport=viewport,
            mode=getattr(self, '_provider_comic_mode', self.preferences.values['comic_layout']))

    async def move_provider_comic(self, direction):
        if self.cloud_busy or self.crypt_reader is None:
            return
        reader = self.crypt_reader
        index = reader.labels.index(self.crypt_page.value)
        nav = reader.comic_navigation
        if direction > 0:
            target = nav.next(index)
        else:
            self.set_cloud_busy(True)
            try:
                target = await asyncio.to_thread(nav.previous, index,
                    viewport=getattr(self, '_provider_viewport', (1, 1)), mode=self.private_comic_mode())
            except Exception as error:
                self.crypt_title.text = private_label('Cannot read previous spread: ' + str(error)[:200])
                return
            finally:
                self.set_cloud_busy(False)
        if target is not None:
            await self.move_private_page(target)


    def watch_provider_epub_width(self):
        task = getattr(self, '_provider_width_task', None)
        if not hasattr(self, 'provider_epub_view'):
            return
        panel = self.provider_epub_view
        if task is not None and not task.done():
            if getattr(self, '_provider_width_panel', None) is panel:
                return
            task.cancel()
        self._provider_width_panel = panel
        from features.books.mobile.presentation import watch_width, pane_width
        def width():
            available = pane_width(self.crypt_content, self.main_window.size.width, 0)
            if hasattr(panel, 'reflow'):
                panel.reflow(available, immersive=self.crypt_immersive)
            return available
        self._provider_width_task = self.loop.create_task(watch_width(
            alive=lambda: getattr(self, 'provider_epub_view', None) is panel,
            width=width, view=lambda: panel))

    def private_comic_seam(self, view=None):
        from .fold_layout import seam_fraction
        return seam_fraction(self, (view or self).crypt_content)

    def private_comic_mode(self):
        from .fold_layout import comic_mode
        return comic_mode(self, getattr(self, 'crypt_content', self.main_window.content))

    def private_comic_viewport(self, view=None):
        layout = (view or self).crypt_content.layout
        return max(1, min(layout.content_width or self.main_window.size.width, self.main_window.size.width)), max(1, layout.content_height or 1)

    def watch_provider_layout(self):
        task = getattr(self, '_provider_layout_task', None)
        reader = self.crypt_reader
        if (reader is None or not hasattr(reader, 'comic_navigation')
                or (task is not None and not task.done())):
            return
        from features.comics.mobile.presentation import watch_layout
        self._provider_layout_task = self.loop.create_task(watch_layout(
            alive=lambda: self.crypt_reader is reader and self.active_host
                and hasattr(self, 'provider_spread') and not getattr(self, 'page_suspended', False),
            available=lambda: not self.cloud_busy and self.manager.active is self,
            viewport=lambda: (self.private_comic_viewport(), self.private_comic_mode(), self.private_comic_seam()),
            view=lambda: getattr(self, 'provider_spread', None), reload=self.read_crypt_page))

    def show_provider_layout(self, widget=None, **kwargs):
        if (self.crypt_reader is None or self.crypt_reader.editable
                or (self.crypt_reader.book is None and self.crypt_reader.kind not in {'.cbz', '.zip'})):
            return
        from features.books.mobile.appearance import ReaderAppearance
        kind = 'epub' if self.crypt_reader.book is not None else 'comic'
        view = ReaderAppearance(self.preferences.values, self.apply_provider_layout, kind=kind)
        self.provider_appearance = view
        if kind == 'epub':
            self.provider_font, self.provider_margin = view.font_choice, view.margin_choice
            self.provider_theme = view.theme_choice
        else:
            self.provider_layout = view.layout_choice
        self.show_view(view, route='private:' + self.session.id + ':layout', title='Reading appearance')

    async def apply_provider_layout(self, widget=None, **kwargs):
        if self.cloud_busy or self.crypt_reader is None:
            return
        try:
            self.preferences.save(**self.provider_appearance.settings())
        except (OSError, ValueError) as error:
            self.provider_appearance.status.text = str(error)
            return
        await self.read_crypt_page()
        self.resume_crypt()

    async def refresh_provider_comic_neighbors(self):
        header = getattr(self, 'comic_header', None)
        reader = self.crypt_reader
        provider = getattr(self._crypt_reader_store, 'provider', None)
        if header is None or reader is None or provider is None:
            return
        header.sync(False, False)
        token = self.workspace.token(self.session.id)
        key = reader.key
        try:
            rows = await asyncio.to_thread(provider.list, key.rpartition('/')[0])
        except Exception:
            return
        if not self.active_host or self.crypt_reader is not reader or not self.workspace.accepts(token):
            return
        from features.comics.mobile.navigation import adjacent_comic
        comics = [(row['path'], row['name']) for row in rows
                  if not row['directory'] and Path(row['name']).suffix.lower() in {'.cbz', '.zip'}]
        header.sync(adjacent_comic(comics, key, -1) is not None,
                    adjacent_comic(comics, key, 1) is not None)

    async def adjacent_provider_comic(self, direction):
        if self.cloud_busy or self.crypt_reader is None or self.crypt_reader.book is not None or self.crypt_reader.editable:
            return
        store = self._crypt_reader_store
        provider = getattr(store, 'provider', None)
        if provider is None:
            self.crypt_title.text = private_label('Open a folder-backed comic to navigate neighboring files.')
            return
        from features.comics.mobile.navigation import adjacent_comic
        key = self.crypt_reader.key
        token = self.workspace.token(self.session.id)
        try:
            rows = await asyncio.to_thread(provider.list, key.rpartition('/')[0])
        except Exception as error:
            self.crypt_title.text = private_label('Cannot list neighboring comics: ' + str(error)[:200])
            return
        if not self.active_host or not self.workspace.accepts(token) or self.manager.active is not self:
            return
        target = adjacent_comic([(row['path'], row['name']) for row in rows
            if not row['directory'] and Path(row['name']).suffix.lower() in {'.cbz', '.zip'}], key, direction)
        if target is not None:
            immersive = self.crypt_immersive
            if await self.manager.open(store, target, destination=self.presentation_destination):
                owner = self.manager.active
                if owner.crypt_immersive != immersive:
                    owner.toggle_private_reading_mode()

    async def previous_provider_comic_file(self, widget=None, **kwargs):
        await self.adjacent_provider_comic(-1)

    async def next_provider_comic_file(self, widget=None, **kwargs):
        await self.adjacent_provider_comic(1)


    def show_provider_read_aloud(self, widget=None, **kwargs):
        panel = getattr(self, 'provider_epub_view', None)
        if panel is not None and hasattr(panel, 'show_read_aloud') and not self.cloud_busy:
            panel.show_read_aloud(self.loop, app=self.app, privacy_gate=lambda: self.privacy_gate,
                valid=lambda: speech_session_valid(self))
