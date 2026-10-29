"""App-hosted provider documents: private drafts, format views and session controls."""
import asyncio
import threading
import textwrap
from pathlib import Path
import toga
from toga.style import Pack
from toga.style.pack import COLUMN

def speech_session_valid(owner):
    if not owner.active_host or owner.crypt_reader is None:
        return False
    try:
        check = getattr(owner, 'document_access', None)
        if check is not None:
            check()
    except ValueError:
        return False
    return True



def private_label(value):
    # Native labels use their longest line as a minimum width. Bound messages
    # and virtual filenames so they cannot widen a phone's entire reader.
    return textwrap.fill(str(value), width=30)




from .files_ui import FilesUI
from .reader_controls import schedule_swipe


def _provider_page_direction(view, kind, index):
    """Preserve spread-half and reading-direction semantics across page changes."""
    from .page_animation import page_direction
    if (kind in {'spread', 'image'} and view.crypt_reader.kind in {'.cbz', '.zip'}
            and view.crypt_content.children):
        previous_index = getattr(view, '_provider_displayed_index', None)
        half = view.crypt_reader.comic_navigation.prepared[1] if kind == 'spread' else 0
        return page_direction(None if previous_index is None else previous_index + getattr(view, '_provider_displayed_half', 0) / 2,
            index + half / 2,
            right_to_left=getattr(view.crypt_reader, 'right_to_left', False))
    elif view.crypt_reader.kind in {'.epub', '.pdf'} and view.crypt_content.children:
        return page_direction(getattr(view, '_provider_displayed_index', None), index)
    return 0


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
    from services.workflow_host import OwnedAttribute

    crypt_reader = OwnedAttribute('provider_document', 'reader')
    _crypt_cancel = OwnedAttribute('provider_document', 'cancel')
    crypt_metadata_fields = OwnedAttribute('provider_document', 'metadata_fields')
    crypt_metadata_initial = OwnedAttribute('provider_document', 'metadata_initial')
    crypt_metadata_values = OwnedAttribute('provider_document', 'metadata_values')

    def provider_document(self):
        from .provider_document import ProviderDocumentSession
        if '_provider_document' not in self.__dict__:
            self._provider_document = ProviderDocumentSession(self)
        return self._provider_document

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
        self.provider_document().dispose()
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
        if hasattr(self, 'crypt_selector'):
            self.crypt_selector.items = []




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
            from features.books.library.metadata import values
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
            from features.books.library.metadata import patch
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
            self._provider_comic_sharing = self.format_services.comic_sharing()
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
        from features.text_editor.access import can_write
        if not can_write(provider=self._crypt_reader_store, reader=self.crypt_reader):
            return
        if self.cloud_busy or self.crypt_reader is None or not self.crypt_reader.editable:
            return
        self.set_cloud_busy(True)
        self.crypt_save.enabled = False
        self.crypt_text.readonly = True
        self._crypt_cancel = threading.Event()
        try:
            workflow = getattr(self, '_provider_markdown', None)
            if workflow is not None:
                await workflow.flush()
            self.crypt_reader = await asyncio.to_thread(self._crypt_reader_store.save, self.crypt_reader, self.crypt_text.value, cancelled=self._crypt_cancel.is_set)
            self.crypt_title.text = private_label(Path(self.crypt_reader.name).name + ' · Saved locally')
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
        """Prepare, validate and mount content before updating session chrome."""
        from .provider_presentation import prepare_comic_spread, prepare_epub_page
        controller = owner or self
        view = self if view is None else view
        from .reading.publication import ReadingPublication
        publication = ReadingPublication.provider(controller, view)
        old_epub = getattr(view, 'provider_epub_view', None)
        prepared_spread = publish_spread = None
        pdf_image = None
        if kind == 'pdf-spread':
            from features.comics.mobile.composite import compose_spread
            pdf_viewport, (pdf_indices, pages) = content
            pdf_image = compose_spread(pages, viewport=pdf_viewport)
        if view.crypt_reader.book is None and kind == 'spread':
            indices, _ = content
            prepared_spread, publish_spread = prepare_comic_spread(controller, view, content)
        index = view.crypt_reader.labels.index(view.crypt_page.value)
        direction = _provider_page_direction(view, kind, index)
        with publication.preparing(direction) as current:
            if not current:
                return
            if view.crypt_reader.book is not None:
                surface = prepare_epub_page(self, controller, view, content)
            elif kind == 'spread':
                from features.comics.mobile.presentation import place_page
                place_page(prepared_spread, controller.format_services.page_region(view.crypt_content))
                surface = prepared_spread
            elif kind == 'pdf-spread':
                view.crypt_image._external_document_page = True
                view.crypt_image.image = pdf_image
                surface = view.crypt_image
            elif kind == 'image':
                view.crypt_image._external_comic_page = view.crypt_reader.kind in {'.cbz', '.zip'}
                view.crypt_image.image = toga.Image(src=content)
                surface = view.crypt_image
            else:
                view.crypt_text.value = content
                surface = view.crypt_text
            if not publication.mount(surface, direction=direction, publish=publish_spread,
                                     keep=(view.crypt_image, view.crypt_text),
                                     retired=(old_epub,) if old_epub is not None else ()):
                return
        if kind == 'pdf-spread':
            view.crypt_reader.pdf_navigation.commit(pdf_indices, pdf_viewport)
        if kind == 'spread':
            view.provider_spread = prepared_spread
            view.crypt_reader.comic_navigation.commit(indices)
            view.crypt_title.text = private_label(f'Page {index + 1}/{len(view.crypt_reader.labels)}' +
                view.crypt_reader.comic_navigation.part_label)
        if surface is not view.crypt_text:
            view.crypt_text.value = ''
        if surface is not view.crypt_image:
            view.crypt_image.image = None
        if old_epub is not None and surface is not getattr(view, 'provider_epub_view', None):
            del view.provider_epub_view
        comic = view.crypt_reader.kind in {'.cbz', '.zip'}
        for child in view.crypt_content.children:
            if hasattr(child, 'magnifier_enabled'):
                child.magnifier_enabled = (comic or view.crypt_reader.kind == '.pdf') and getattr(view, 'crypt_immersive', False)
        view._provider_displayed_half = view.crypt_reader.comic_navigation.half if kind == 'spread' else 0
        previous_index = getattr(view, '_provider_displayed_index', None)
        view._provider_displayed_index = view.crypt_reader.labels.index(view.crypt_page.value)
        if (view.crypt_reader.kind == '.pdf' and hasattr(view, 'pdf_number')
                and previous_index != view._provider_displayed_index):
            view.pdf_number.value = str(view._provider_displayed_index + 1)
        publication.chrome()

    async def read_crypt_page(self, widget=None, *, preserve_speech=False, **kwargs):
        if self.cloud_busy or self.crypt_reader is None or self.crypt_reader.editable:
            return
        panel = getattr(self, 'provider_epub_view', None)
        if not preserve_speech and panel is not None and hasattr(panel, 'close_read_aloud'):
            panel.close_read_aloud()
        self.set_cloud_busy(True)
        self.crypt_read_page.enabled = False
        try:
            index = self.crypt_reader.labels.index(self.crypt_page.value)
            if self.crypt_reader.kind == '.pdf':
                from features.pdf.mobile.canvas import pdf_viewport
                self._provider_viewport = pdf_viewport(self)
            else:
                self._provider_viewport = self.private_comic_viewport()
            self._provider_comic_mode = self.private_comic_mode()
            self._provider_comic_sharing = self.format_services.comic_sharing()
            self._provider_comic_seam = self.private_comic_seam()
            reader = self.crypt_reader
            from .reading.publication import ReadingPublication
            publication = ReadingPublication.provider(self, self)
            kind, content = await asyncio.to_thread(self.provider_page_content, reader, index)
            if not publication.current() or self.manager.active is not self:
                return
            self._show_crypt_content(kind, content)
            self.page_suspended = False
            if reader.kind in {'.pdf', '.cbz', '.zip'}:
                self.crypt_title.text = private_label(f'Page {index + 1}/{len(reader.labels)}' +
                    (reader.comic_navigation.part_label if hasattr(reader, 'comic_navigation') else ''))
            self.refresh_private_bookmarks()
            self.watch_provider_layout()
            self.watch_provider_epub_width()
            panel = self.provider_epub_view if reader.book is not None else None
            publication.footer(self, comic=reader.kind in {'.cbz', '.zip'}, count=len(reader.labels),
                               index=index, right_to_left=getattr(reader, 'right_to_left', False),
                               chapter=(panel.offset, panel.chapter.length) if panel is not None else None)
            self.previous_page.enabled = reader.book is not None or (reader.comic_navigation.can_previous(index) if hasattr(reader, 'comic_navigation') else index > 0)
            self.next_page.enabled = reader.book is not None or (reader.comic_navigation.next(index) is not None if hasattr(reader, 'comic_navigation') else index + 1 < len(reader.labels))
            if reader.kind == '.pdf':
                from features.pdf.mobile.canvas import sync_pdf_progress
                sync_pdf_progress(self)
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
        if getattr(self.crypt_reader, 'kind', None) == '.pdf':
            async def turn(direction):
                if direction > 0:
                    await self.next_private_page()
                else:
                    await self.previous_private_page()
            schedule_swipe(self, direction, right_to_left=False, busy=self.cloud_busy, move=turn)
            return
        if hasattr(self.crypt_reader, 'comic_navigation'):
            schedule_swipe(self, direction, right_to_left=getattr(self.crypt_reader, 'right_to_left', False),
                           busy=self.cloud_busy, move=self.move_provider_comic)
            return
        schedule_swipe(self, direction, position=self.crypt_reader.labels.index(self.crypt_page.value),
                       count=len(self.crypt_reader.labels), right_to_left=getattr(self.crypt_reader, 'right_to_left', False),
                       busy=self.cloud_busy, move=self.move_private_page)

    async def move_private_page(self, index, *, preserve_speech=False):
        if self.cloud_busy or self.crypt_reader is None or not 0 <= index < len(self.crypt_reader.labels):
            return
        self.crypt_page.value = self.crypt_reader.labels[index]
        await self.read_crypt_page(**({'preserve_speech': True} if preserve_speech else {}))

    async def previous_private_page(self, widget=None, **kwargs):
        if self.crypt_reader is not None and self.crypt_reader.kind == '.pdf':
            if self.cloud_busy:
                return
            reader = self.crypt_reader
            token = self.workspace.token(self.session.id)
            self.set_cloud_busy(True)
            try:
                target = await asyncio.to_thread(reader.pdf_navigation.previous)
            except Exception as error:
                if self.crypt_reader is reader and self.workspace.accepts(token):
                    self.crypt_title.text = private_label('Cannot read previous pages: ' + str(error)[:200])
                return
            finally:
                self.set_cloud_busy(False)
            if self.crypt_reader is reader and self.workspace.accepts(token) and target is not None:
                await self.move_private_page(target)
            return
        if self.crypt_reader is not None and hasattr(self.crypt_reader, 'comic_navigation'):
            await self.move_provider_comic(-1)
            return
        if hasattr(self, 'provider_epub_view') and self.provider_epub_view.turn(-1):
            return
        if self.crypt_reader is not None:
            await self.move_private_page(self.crypt_reader.labels.index(self.crypt_page.value) - 1)

    async def next_private_page(self, widget=None, **kwargs):
        if self.crypt_reader is not None and self.crypt_reader.kind == '.pdf':
            target = self.crypt_reader.pdf_navigation.next()
            if target is not None:
                await self.move_private_page(target)
            return
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
        if reader.kind == '.pdf':
            from features.pdf.mobile.canvas import PDFNavigation
            if not hasattr(reader, 'pdf_navigation'):
                reader.pdf_navigation = PDFNavigation(reader.pdf)
            viewport = getattr(self, '_provider_viewport', (1, 1))
            return 'pdf-spread', (viewport, reader.pdf_navigation.load(index, viewport))
        if reader.book is not None or reader.editable or getattr(reader, 'image_document', False):
            return reader.page(index)
        from features.comics.mobile.navigation import provider_navigation
        if not hasattr(reader, 'comic_navigation'):
            reader.comic_navigation = provider_navigation(reader)
        viewport = getattr(self, '_provider_viewport', (1, 1))
        return 'spread', reader.comic_navigation.load(index, viewport=viewport,
            mode=getattr(self, '_provider_comic_mode', self.preferences.values['comic_layout']),
            anchor_right=getattr(self, '_provider_comic_seam', None) is not None,
            split_wide=(self.preferences.values.get('comic_split_wide', 'true') == 'true'
                        and not getattr(self, '_provider_comic_sharing', False)))

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
