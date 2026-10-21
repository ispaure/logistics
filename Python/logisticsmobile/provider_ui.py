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


class _MarkdownState:
    """Compatibility names expose the workflow's single state owner."""
    def __init__(self, name):
        self.name = name
        self.fallback = '_legacy_markdown_' + name

    def __get__(self, owner, cls=None):
        if owner is None:
            return self
        workflow = owner.__dict__.get('_provider_markdown')
        if workflow is not None:
            return getattr(workflow, self.name)
        if self.fallback in owner.__dict__:
            return owner.__dict__[self.fallback]
        raise AttributeError(self.name)

    def __set__(self, owner, value):
        workflow = owner.__dict__.get('_provider_markdown')
        if workflow is not None:
            setattr(workflow, self.name, value)
        else:
            owner.__dict__[self.fallback] = value


class ProviderUI(FilesUI):
    crypt_preview = _MarkdownState('preview')
    crypt_formatted = _MarkdownState('formatted')
    crypt_preview_search = _MarkdownState('search')
    markdown_speech = _MarkdownState('speech')
    crypt_markdown_mode = _MarkdownState('mode')
    _private_preview_token = _MarkdownState('token')
    _private_preview_pending = _MarkdownState('pending')
    _text_menu_state = _MarkdownState('menu_state')
    crypt_actions_menu = _MarkdownState('actions_menu')


    def private_dirty(self):
        return bool(self.crypt_reader and ((self.crypt_reader.editable and self.crypt_text.value != self.crypt_reader.text)
                    or any(field.value != self.crypt_metadata_initial[key] for key, field in self.crypt_metadata_fields.items())))

    def resume_crypt(self, widget=None, **kwargs):
        if self.crypt_reader is not None:
            self.show_view(self.crypt_view)

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
        from .page_animation import cancel_page_slide
        cancel_page_slide(getattr(self, 'crypt_content', None))
        from .ios_content_background import clear
        clear(getattr(self, 'app', self))
        self.crypt_reader = None
        for field in self.crypt_metadata_fields.values():
            field.value = ''
        self.crypt_metadata_fields = {}
        self.crypt_metadata_initial = {}
        self.crypt_metadata_values = {}
        if hasattr(self, 'crypt_metadata_view'):
            self.crypt_metadata_view.content = None
            self.crypt_metadata_status.text = ''
        workflow = getattr(self, '_provider_markdown', None)
        if workflow is not None:
            workflow.dispose()
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
        from .external_display import sync as sync_external
        sync_external(getattr(self, 'app', self))
        return True

    def clear_private_catalog(self):
        self.app.routes.folders.invalidate_private()
        factory = getattr(self.app, 'folder_controller', None)
        if factory is not None:
            factory().invalidate_folder_discovery()
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
            drawer.listing.invalidate()
            drawer.scoped_provider = None
            if drawer.provider is not None and drawer.provider.private:
                drawer.provider = None
                drawer.browser.stop()
                drawer.status.text = 'Private folders locked. Choose an available location.'
            if drawer.destination == 'documents':
                drawer.refresh_menu()
        self.editor_picker().clear()
        ordinary = self.ordinary_file_roots() if hasattr(self, 'files_view') else {}
        previous_roots = getattr(self, 'file_roots', {})
        for label, provider in list(ordinary.items()):
            previous = previous_roots.get(label)
            if (previous is provider or (previous is not None and provider is not None
                    and not previous.private and previous.root == provider.root)):
                ordinary[label] = previous
        keep_local = (hasattr(self, 'files_view') and self.file_storage.value in ordinary
                      and not getattr(self.file_provider, 'private', False))
        listing = getattr(self, '_folder_listing', None)
        if listing is not None and not keep_local:
            listing.invalidate()
        for name in ('file_browser', 'remote_browser'):
            browser = getattr(self, name, None)
            if browser is not None and not (name == 'file_browser' and keep_local):
                browser.stop()
        if hasattr(self, 'files_view'):
            storage, destination = self.file_storage.value, self.file_destination.value
            self.file_changing_location = True
            try:
                self.file_roots = ordinary
                self.file_storage.items = self.file_destination.items = list(ordinary)
                default = self.local_browser_root()
                self.file_storage.value = storage if storage in ordinary else default
                self.file_destination.value = destination if destination in ordinary else default
            finally:
                self.file_changing_location = False
            if not keep_local:
                self.file_rows = {}
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
                from .loading_progress import opening_options
                reader = await asyncio.to_thread(copies.open, key,
                    password=password, cancelled=self._crypt_cancel.is_set, **opening_options(copies))
                self._provider_comic_mode = self.private_comic_mode()
                self._provider_comic_seam = self.private_comic_seam()
                self._provider_viewport = (max(1, self.main_window.size.width), max(1, self.main_window.size.height))
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
                        int(self.preferences.values['markdown_font_size']), image_source=reader_image_source(copies, reader))
                except ValueError as error:
                    # Keep the established source fallback and error feedback.
                    initial_preview_error = str(error)
            check_cancelled(self._crypt_cancel.is_set)
            from types import SimpleNamespace
            view = SimpleNamespace()
            view.crypt_reader = reader
            view._crypt_reader_store = copies
            view.crypt_title = toga.Label(private_label(Path(reader.name).name), style=Pack(font_size=18))
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
            from .font_scaling import bind, font_size
            view.crypt_text = CodeInput(loop=self.loop, filename=reader.name, readonly=not reader.editable,
                highlighting=self.preferences.values.get('android_eink') != 'true',
                on_change=self.private_source_changed,
                style=Pack(flex=1, font_size=font_size(self, reader.kind)))
            bind(self, view.crypt_text, reader.kind)
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
            if not self.show_view(view.crypt_view, checkpoint=not handoff, title=Path(reader.name).name):
                return False
            self._crypt_cancel = None
            self.clear_private_reader(discard=True)
            self._provider_markdown = getattr(view, '_provider_markdown', None)
            for name, value in vars(view).items():
                if self._provider_markdown is not None and isinstance(getattr(type(self), name, None), _MarkdownState):
                    continue
                setattr(self, name, value)
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
            else:
                await self.main_window.dialog(toga.InfoDialog('Could not open document', str(error)[:300]))
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
        children = [toga.Label(private_label('Edit metadata: ' + Path(reader.name).name)), self.crypt_metadata_status]
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
            self._provider_comic_seam = self.private_comic_seam()
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
            self.crypt_title.text = private_label(Path(self.crypt_reader.name).name + (' · Saved encrypted locally' if getattr(self._crypt_reader_store, 'encrypted', True) else ' · Saved locally'))
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
        prepared_spread = publish_spread = None
        if view.crypt_reader.book is None and kind == 'spread':
            from features.comics.mobile.presentation import SpreadView
            from commonUtils.ui.native.image_canvas import ImageCanvas
            indices, data = content
            # Decode/compose before retiring the displayed private pixels. Native
            # allocation or decoder failures must preserve the previous spread.
            previous = getattr(view, 'provider_spread', None)
            if isinstance(previous, SpreadView) and previous in view.crypt_content.children:
                prepared_spread = previous
                publish_spread = previous.prepare_replacement(data,
                    right_to_left=getattr(view.crypt_reader, 'right_to_left', False),
                    viewport=controller.private_comic_viewport(view), seam=controller.private_comic_seam(view),
                    crop=view.crypt_reader.comic_navigation.crop,
                    seam_gap=controller.format_services.seam_gap(view.crypt_content),
                    anchor_right=controller.private_comic_seam(view) is not None)
            else:
                prepared_spread = SpreadView(data, canvas=ImageCanvas,
                    on_page=controller.swipe_crypt_page, on_toggle=controller.toggle_private_reading_mode,
                    right_to_left=getattr(view.crypt_reader, 'right_to_left', False),
                    viewport=controller.private_comic_viewport(view),
                    seam=controller.private_comic_seam(view),
                    crop=view.crypt_reader.comic_navigation.crop,
                    seam_gap=controller.format_services.seam_gap(view.crypt_content),
                    anchor_right=controller.private_comic_seam(view) is not None)
            from .magnifier import bind
            bind(controller, prepared_spread)
        from .page_animation import page_direction, begin_page_slide, finish_page_slide
        index = view.crypt_reader.labels.index(view.crypt_page.value)
        direction = 0
        if (kind in {'spread', 'image'} and view.crypt_reader.kind in {'.cbz', '.zip'}
                and view.crypt_content.children):
            previous_index = getattr(view, '_provider_displayed_index', None)
            half = view.crypt_reader.comic_navigation.prepared[1] if kind == 'spread' else 0
            direction = page_direction(None if previous_index is None else previous_index + getattr(view, '_provider_displayed_half', 0) / 2,
                index + half / 2,
                right_to_left=getattr(view.crypt_reader, 'right_to_left', False))
        elif view.crypt_reader.kind in {'.epub', '.pdf'} and view.crypt_content.children:
            direction = page_direction(getattr(view, '_provider_displayed_index', None), index)
        begin_page_slide(view.crypt_content, direction, self.preferences.values)
        if publish_spread is not None:
            publish_spread()
        for child in list(view.crypt_content.children):
            if hasattr(child, 'dispose') and child not in (view.crypt_image, view.crypt_text, prepared_spread):
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
                offset = content[1].anchors.get(target, 0) if isinstance(target, str) else target
            from .palette import themed_chapter
            content = (themed_chapter(content[0], self.preferences.values['reading_theme']), content[1])
            def position_changed(value):
                locations[book.spine[index]] = value
                if hasattr(view, 'page_footer'):
                    view.page_footer.chapter_progress(index, len(book.spine), value, content[1].length)
            from .chapter_drawer import ChapterDrawer
            view.provider_epub_view = provider_view(book, index, offset=offset, prepared=content,
                font_size=int(self.preferences.values['epub_font_size']),
                margin=int(self.preferences.values['reading_margin']), theme=self.preferences.values['reading_theme'], typography=typography_options(self.preferences.values),
                on_chapter=controller.open_provider_epub_chapter,
                on_position=position_changed,
                motion_enabled=self.preferences.values.get('android_eink') != 'true',
                sidebar_factory=lambda *args, **kwargs: ChapterDrawer(*args, app=self, **kwargs))
            from .font_scaling import bind
            epub_surface = getattr(view.provider_epub_view, 'webview', None)
            if epub_surface is not None:
                from .fold_layout import bind_epub_geometry
                bind_epub_geometry(epub_surface)
                bind(self, epub_surface, 'epub', web=True)
            else:
                bind(self, view.provider_epub_view.text, 'epub')
            chapters = getattr(view.provider_epub_view, 'chapters', None)
            if chapters is not None:
                from .appearance import hierarchy_row_style
                chapters.row_style, chapters.current = hierarchy_row_style, index
                chapters.render()
            view.provider_epub_view.page_motion_enabled = lambda: self.preferences.values.get('android_eink') != 'true'
            if epub_surface is None:
                view.provider_epub_view.page_motion = (
                    lambda surface, delta: begin_page_slide(surface, delta, self.preferences.values),
                    lambda surface, delta: finish_page_slide(surface, delta, self.preferences.values))
            tools = view.provider_epub_view.tools
            if tools.button in tools.widget.children:
                tools.widget.remove(tools.button)
            for control in (view.crypt_bookmark_button, view.crypt_bookmark_selector):
                if control.parent is not None:
                    control.parent.remove(control)
                tools.panel.add(control)
            tools.panel.add(toga.Label('Bookmarks stay in this session\nand are cleared on close.'))
            view.crypt_content.add(view.provider_epub_view)
        elif kind == 'spread':
            from features.comics.mobile.presentation import place_page
            place_page(prepared_spread, controller.format_services.page_region(view.crypt_content))
            view.provider_spread = prepared_spread
            view.crypt_content.add(prepared_spread)
            view.crypt_reader.comic_navigation.commit(indices)
            view.crypt_title.text = private_label(f'Page {index + 1}/{len(view.crypt_reader.labels)}' +
                view.crypt_reader.comic_navigation.part_label)
        elif kind == 'image':
            view.crypt_image._external_comic_page = view.crypt_reader.kind in {'.cbz', '.zip'}
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
        view._provider_displayed_half = view.crypt_reader.comic_navigation.half if kind == 'spread' else 0
        view._provider_displayed_index = view.crypt_reader.labels.index(view.crypt_page.value)
        if view.crypt_reader.kind == '.pdf' and hasattr(view, 'pdf_number'):
            view.pdf_number.value = str(view._provider_displayed_index + 1)
        from .external_display import sync as sync_external
        sync_external(getattr(controller, 'app', controller))

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
            self._provider_comic_seam = self.private_comic_seam()
            reader = self.crypt_reader
            token = self.workspace.token(self.session.id)
            kind, content = await asyncio.to_thread(self.provider_page_content, reader, index)
            if (not self.active_host or self.crypt_reader is not reader
                    or not self.workspace.accepts(token) or self.manager.active is not self):
                return
            self._show_crypt_content(kind, content)
            self.page_suspended = False
            if reader.kind in {'.pdf', '.cbz', '.zip'}:
                self.crypt_title.text = private_label(f'Page {index + 1}/{len(reader.labels)}' +
                    (reader.comic_navigation.part_label if hasattr(reader, 'comic_navigation') else ''))
            self.refresh_private_bookmarks()
            self.watch_provider_layout()
            self.watch_provider_epub_width()
            self.page_footer.sync(comic=reader.kind in {'.cbz', '.zip'}, count=len(reader.labels),
                                  index=index, right_to_left=getattr(reader, 'right_to_left', False))
            if reader.book is not None:
                panel = self.provider_epub_view
                self.page_footer.chapter_progress(index, len(reader.labels), panel.offset, panel.chapter.length)
            self.previous_page.enabled = reader.book is not None or (reader.comic_navigation.can_previous(index) if hasattr(reader, 'comic_navigation') else index > 0)
            self.next_page.enabled = reader.book is not None or (reader.comic_navigation.next(index) is not None if hasattr(reader, 'comic_navigation') else index + 1 < len(reader.labels))
        except Exception as error:
            self.crypt_title.text = private_label('Cannot read page: ' + str(error)[:200])
            if self.crypt_reader is not None:
                self.crypt_page.value = self.crypt_reader.labels[getattr(self, '_provider_displayed_index', 0)]
            if getattr(self, 'page_suspended', False) and getattr(self, 'crypt_immersive', False):
                # A released fullscreen page has no pixels or controls to tap.
                # Expose the error, retry and Close instead of trapping the user.
                self.toggle_private_reading_mode()
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
        from .provider_presentation import compact_private_view
        return compact_private_view(self, view)

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
        workflow = getattr(self, '_provider_markdown', None)
        if workflow is not None:
            return workflow.clear()

    def refresh_private_text_controls(self, *, view=None):
        owner = view or self
        workflow = getattr(owner, '_provider_markdown', None)
        if workflow is not None:
            return workflow.refresh_controls(reader=getattr(owner, 'crypt_reader', None))
        reader = getattr(owner, 'crypt_reader', None)
        toolbar = getattr(owner, 'reader_toolbar', None)
        if reader is None or toolbar is None or not reader.editable:
            return
        dirty = owner.crypt_text.value != reader.text and not getattr(reader, 'read_only', False)
        owner.crypt_save.enabled = dirty and not self.cloud_busy
        native_toolbar = type(toolbar._impl).__module__.startswith('toga_iOS.')
        if dirty and not native_toolbar and owner.crypt_save not in toolbar.children:
            toolbar.insert(len(toolbar.children) - 1, owner.crypt_save)
        elif not dirty and owner.crypt_save in toolbar.children:
            toolbar.remove(owner.crypt_save)
        buttons = getattr(owner, '_native_reading_buttons', None)
        if buttons is not None:
            buttons[:] = ([owner.crypt_save] if dirty else []) + [owner.crypt_actions]
            app = getattr(self, 'app', self)
            if owner.crypt_view in app.routes.body().children:
                from .workspace_navigation import sync_reader_toolbar
                sync_reader_toolbar(app, owner.crypt_view)

    def private_source_changed(self, widget, **kwargs):
        if widget is not getattr(self, 'crypt_text', None):
            return
        workflow = getattr(self, '_provider_markdown', None)
        if workflow is not None:
            return workflow.source_changed(widget, **kwargs)
        self.refresh_private_text_controls()

    def schedule_private_preview(self, *, delay=0):
        workflow = getattr(self, '_provider_markdown', None)
        if workflow is not None:
            return workflow.schedule_preview(delay=delay)

    def toggle_private_preview(self, widget=None, *, initial=False, rendered=None, **kwargs):
        workflow = getattr(self, '_provider_markdown', None)
        if workflow is not None:
            return workflow.toggle_preview(widget, initial=initial, rendered=rendered, **kwargs)

    def private_edit_mode_changed(self, widget=None, **kwargs):
        workflow = getattr(self, '_provider_markdown', None)
        if workflow is not None:
            return workflow.edit_mode_changed(widget, **kwargs)

    def show_private_markdown_editor(self):
        workflow = getattr(self, '_provider_markdown', None)
        if workflow is not None:
            return workflow.show_editor()

    def show_private_tools(self, widget=None, **kwargs):
        if not self.cloud_busy:
            title = 'Comic pages' if self.crypt_reader is not None and self.crypt_reader.kind in {'.cbz', '.zip'} else 'Private document actions'
            self.show_view(self.crypt_tools_view, route='private-tools', title=title)

    async def show_provider_comic_info(self, *args, **kwargs):
        return await self.provider_comic_controller().show_provider_comic_info(*args, **kwargs)

    def fit_private_page(self, *args, **kwargs):
        return self.provider_comic_controller().fit_private_page(*args, **kwargs)

    def close_crypt(self, widget=None, **kwargs):
        if not self.cloud_busy and self.clear_private_reader():
            self.show_cloud()


    def show_provider_epub_find(self, *args, **kwargs):
        result = self.provider_book_controller().show_provider_epub_find(*args, **kwargs)
        self.app.adaptive.render()
        return result

    def toggle_provider_epub_tools(self, *args, **kwargs):
        return self.provider_book_controller().toggle_provider_epub_tools(*args, **kwargs)

    async def show_provider_epub_navigation(self, *args, **kwargs):
        return await self.provider_book_controller().show_provider_epub_navigation(*args, **kwargs)

    def open_provider_epub_chapter(self, *args, **kwargs):
        return self.provider_book_controller().open_provider_epub_chapter(*args, **kwargs)


    def provider_page_content(self, reader, index):
        if reader.book is not None:
            from features.books.mobile.content import indexed_chapter
            from features.books.mobile.typography import options
            return 'epub', indexed_chapter(reader.book, index,
                int(self.preferences.values['epub_font_size']),
                margin=int(self.preferences.values['reading_margin']),
                theme=self.preferences.values['reading_theme'], links=True,
                **options(self.preferences.values))
        if reader.kind == '.pdf' or reader.book is not None or reader.editable or getattr(reader, 'image_document', False):
            return reader.page(index)
        from features.comics.mobile.navigation import provider_navigation
        if not hasattr(reader, 'comic_navigation'):
            reader.comic_navigation = provider_navigation(reader)
        viewport = getattr(self, '_provider_viewport', (1, 1))
        return 'spread', reader.comic_navigation.load(index, viewport=viewport,
            mode=getattr(self, '_provider_comic_mode', self.preferences.values['comic_layout']),
            anchor_right=getattr(self, '_provider_comic_seam', None) is not None,
            split_wide=self.preferences.values.get('comic_split_wide', 'true') == 'true')

    async def move_provider_comic(self, *args, **kwargs):
        return await self.provider_comic_controller().move_provider_comic(*args, **kwargs)


    def watch_provider_epub_width(self, *args, **kwargs):
        return self.provider_book_controller().watch_provider_epub_width(*args, **kwargs)

    def private_comic_seam(self, *args, **kwargs):
        return self.provider_comic_controller().private_comic_seam(*args, **kwargs)

    def private_comic_mode(self, *args, **kwargs):
        return self.provider_comic_controller().private_comic_mode(*args, **kwargs)

    def private_comic_viewport(self, *args, **kwargs):
        return self.provider_comic_controller().private_comic_viewport(*args, **kwargs)

    def watch_provider_layout(self, *args, **kwargs):
        return self.provider_comic_controller().watch_provider_layout(*args, **kwargs)

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
            from .font_scaling import refresh
            refresh(self)
        except (OSError, ValueError) as error:
            self.provider_appearance.status.text = str(error)
            return
        await self.read_crypt_page()
        self.resume_crypt()

    async def refresh_provider_comic_neighbors(self, *args, **kwargs):
        return await self.provider_comic_controller().refresh_provider_comic_neighbors(*args, **kwargs)

    async def adjacent_provider_comic(self, *args, **kwargs):
        return await self.provider_comic_controller().adjacent_provider_comic(*args, **kwargs)

    async def previous_provider_comic_file(self, *args, **kwargs):
        return await self.provider_comic_controller().previous_provider_comic_file(*args, **kwargs)

    async def next_provider_comic_file(self, *args, **kwargs):
        return await self.provider_comic_controller().next_provider_comic_file(*args, **kwargs)


    def show_provider_read_aloud(self, *args, **kwargs):
        return self.provider_book_controller().show_provider_read_aloud(*args, **kwargs)
