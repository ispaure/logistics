"""Native LocalCrypt reader/editor with no document/library persistence."""
import asyncio
import threading
import textwrap
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

def private_label(value):
    # Native labels use their longest line as a minimum width. Bound messages
    # and virtual filenames so they cannot widen a phone's entire reader.
    return textwrap.fill(str(value), width=30)


from .localcrypt import LocalCryptCopies
from commonUtils.runtime.operations import check_cancelled


from .files_ui import FilesUI
from .reader_controls import ReadingFrame, page_buttons, schedule_swipe


class LocalCryptUI(FilesUI):
    def build_localcrypt(self):
        self.crypt_copies = LocalCryptCopies(self.private_root / 'LocalCrypt', self.cloud_client)
        self._crypt_cancel = None
        self.crypt_labels = {}
        self.crypt_selector = toga.Selection(style=Pack(height=44))
        self.crypt_refresh = toga.Button('Refresh encrypted copies', on_press=self.refresh_crypt, style=Pack(height=44))
        self.crypt_download = toga.Button('Download encrypted copy', on_press=self.download_crypt, style=Pack(height=44))
        self.crypt_open = toga.Button('Read encrypted copy', on_press=self.open_crypt, style=Pack(height=44))
        self.crypt_password = toga.PasswordInput(placeholder='Inner ZIP password (if needed)', style=Pack(height=44))
        self.crypt_resume = toga.Button('Return to private reader/editor', on_press=self.resume_crypt, style=Pack(height=44))
        return [self.crypt_download, toga.Label('LocalCrypt · encrypted offline copies'),
                self.crypt_selector, self.crypt_refresh, self.crypt_password, self.crypt_open, self.crypt_resume, self.build_file_manager()]

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
        if hasattr(self, 'crypt_text'):
            self.crypt_text.value = ''
        if hasattr(self, 'crypt_image'):
            self.crypt_image.dispose()
        if hasattr(self, 'crypt_page'):
            self.crypt_page.items = []
        if hasattr(self, 'crypt_bookmarks'):
            self.crypt_bookmarks.clear()
            self.crypt_bookmark_selector.items = []
        if hasattr(self, 'crypt_title'):
            self.crypt_title.text = private_label('Encrypted copy closed')
        if hasattr(self, 'crypt_password'):
            self.crypt_password.value = ''
        return True

    def clear_private_catalog(self):
        self.hub_crypt_locations = []
        self.invalidate_mirror_review()
        self.editor_linked_roots = {}
        if hasattr(self, 'pull_jobs'):
            self.pull_jobs.forget_private()
        if hasattr(self, 'pull_job_box'):
            for child in list(self.pull_job_box.children):
                self.pull_job_box.remove(child)
            self.pull_job_box.add(toga.Label('Folder pulls locked. Reopen from Files.'))
            self.pull_message = ''
        for name in ('file_browser', 'editor_browser', 'remote_browser'):
            browser = getattr(self, name, None)
            if browser is not None:
                browser.stop()
        self.save_as_data = None
        self.save_as_source_document = None
        self.editor_picker_rows = {}
        self.editor_picker_location = None
        if hasattr(self, 'picker_entries'):
            self.picker_entries.items = []
            self.picker_folder.value = ''
        if hasattr(self, 'save_as_view'):
            self.save_as_name.value = ''
            self.save_as_storage.items = []
            self.save_as_status.value = ''
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

    async def refresh_crypt(self, widget=None, **kwargs):
        if self.cloud_busy or self.cloud_client is None:
            return
        self.set_cloud_busy(True)
        try:
            rows = await asyncio.to_thread(self.crypt_copies.items)
            self.crypt_labels = {f'{i + 1}. {name}': key for i, (key, name) in enumerate(rows)}
            self.crypt_selector.items = list(self.crypt_labels)
        except Exception:
            self.cloud_status.value = 'Encrypted copies could not be listed.'
        finally:
            self.set_cloud_busy(False)

    async def download_crypt(self, widget=None, **kwargs):
        row = self.cloud_rows.get(self.cloud_entries.value)
        if self.cloud_busy or not row or row['directory'] or self.cloud_remote.value != self.cloud_open_remote:
            return
        self.set_cloud_busy(True)
        try:
            key = await asyncio.to_thread(self.crypt_copies.fetch, self.cloud_open_remote, row['path'])
            self.cloud_status.value = 'Encrypted copy saved. Reading it does not create a plaintext library copy.'
        except Exception as error:
            self.cloud_status.value = 'Encrypted download failed: ' + str(error)[:300]
            return
        finally:
            self.set_cloud_busy(False)
        await self.refresh_crypt()
        self.crypt_selector.value = next((label for label, value in self.crypt_labels.items() if value == key), None)

    async def open_crypt(self, widget=None, *, copies=None, key=None, prepared=None, independent=False, **kwargs):
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
        try:
            if prepared is None:
                reader = await asyncio.to_thread(copies.open, key, password=password, cancelled=self._crypt_cancel.is_set)
                kind, content = await asyncio.to_thread(reader.page, 0)
            else:
                reader, kind, content = prepared
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
            view.crypt_bookmark_button = toga.Button('Bookmark', on_press=self.toggle_private_bookmark,
                                                    enabled=not reader.editable, style=Pack(height=44))
            view.crypt_bookmark_selector = toga.Selection(items=['Bookmarks…'],
                on_change=self.select_private_bookmark, enabled=not reader.editable, style=Pack(height=44))
            view.crypt_text = toga.MultilineTextInput(readonly=not reader.editable,
                style=Pack(flex=1, font_size=int(self.preferences.values['font_size'])))
            from commonUtils.ui.native.image_canvas import ImageCanvas
            view.crypt_image = ImageCanvas(on_page=self.swipe_crypt_page,
                on_toggle=self.toggle_private_reading_mode, style=Pack(flex=1))
            view.crypt_content = toga.Box(style=Pack(direction=COLUMN, flex=1))
            self._show_crypt_content(kind, content, view=view)
            view.crypt_save = toga.Button('Save encrypted copy' if getattr(copies, 'encrypted', True) else 'Save local file', on_press=self.save_crypt, enabled=reader.editable, style=Pack(height=44))
            view.crypt_read_page.enabled = not reader.editable
            view.crypt_view = toga.Box(children=[view.crypt_title, view.crypt_page, view.crypt_read_page, view.crypt_content,
                view.crypt_save,
                toga.Button('Open…', on_press=self.show_editor_open, style=Pack(height=44)),
                toga.Button('Save As…', on_press=self.show_crypt_save_as, enabled=reader.editable, style=Pack(height=44)),
                toga.Button('Edit metadata…', on_press=self.edit_crypt_metadata, enabled=not reader.editable, style=Pack(height=44)),
                toga.Label(private_label('Edits stay in memory until saved to the selected local file.' if reader.editable else 'Reading position stays in this session')),
                toga.Button('Cancel request', on_press=self.cancel_cloud, style=Pack(height=44)),
                toga.Button('Discard changes and close', on_press=self.discard_crypt, style=Pack(height=44)),
                toga.Button('Close private reader', on_press=self.close_crypt, style=Pack(height=44))],
                style=Pack(direction=COLUMN, flex=1, margin=12))
            self.compact_private_view(view)
            handoff = (prepared is not None and getattr(self, 'save_as_source_document', None) is self.current
                       and getattr(self.current, 'private', False))
            if not self.show_view(view.crypt_view, checkpoint=not handoff, destination='documents'):
                return False
            self._crypt_cancel = None
            self.clear_private_reader(discard=True)
            self.__dict__.update(vars(view))
            return True
        except Exception as error:
            self.cloud_status.value = 'Private reading failed: ' + str(error)[:300]
        finally:
            password = None
            self._crypt_cancel = None
            if not independent:
                self.set_cloud_busy(False)

    def edit_crypt_metadata(self, widget=None, **kwargs):
        if self.cloud_busy or self.crypt_reader is None or self.crypt_reader.editable:
            return
        if self.crypt_metadata_fields:
            self.show_view(self.crypt_metadata_view)
            return
        reader = self.crypt_reader
        if reader.kind == '.epub':
            from features.books.metadata import EDITABLE
            values = {key: reader.book.values(key) for key in EDITABLE}
            self.crypt_metadata_values = values
            initial = {key: '\n'.join(value) if key in {'creator', 'subject'} else next(iter(value), '') for key, value in values.items()}
        else:
            try:
                initial = {key: reader.comic.info.get_field(key) for key in reader.comic.info.FIELDS if key != 'PageCount'}
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
        if self.cloud_busy or self.crypt_reader is None:
            return
        changes = {}
        for key, field in self.crypt_metadata_fields.items():
            if field.value == self.crypt_metadata_initial[key]:
                continue
            value = field.value
            if self.crypt_reader.kind == '.epub':
                value = value.splitlines() if key in {'creator', 'subject'} else [value] + self.crypt_metadata_values[key][1:]
            changes[key] = value
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
        except Exception as error:
            self.crypt_metadata_status.text = private_label('Save failed; edits retained: ' + str(error)[:200])
        finally:
            self._crypt_cancel = None
            self.crypt_metadata_save.enabled = True
            for field in self.crypt_metadata_fields.values():
                field.readonly = False
            self.set_cloud_busy(False)

    async def save_crypt(self, widget=None, **kwargs):
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

    def discard_crypt(self, widget=None, **kwargs):
        if not self.cloud_busy and self.clear_private_reader(discard=True):
            self.show_cloud()

    def _show_crypt_content(self, kind, content, *, view=None):
        view = self if view is None else view
        for child in list(view.crypt_content.children):
            view.crypt_content.remove(child)
        view.crypt_text.value = ''
        view.crypt_image.image = None
        if kind == 'image':
            view.crypt_image.image = toga.Image(src=content)
            view.crypt_content.add(view.crypt_image)
        else:
            view.crypt_text.value = content
            view.crypt_content.add(view.crypt_text)

    async def read_crypt_page(self, widget=None, **kwargs):
        if self.cloud_busy or self.crypt_reader is None or self.crypt_reader.editable:
            return
        self.set_cloud_busy(True)
        self.crypt_read_page.enabled = False
        try:
            index = self.crypt_reader.labels.index(self.crypt_page.value)
            reader = self.crypt_reader
            token = self.workspace.token(self.session.id)
            kind, content = await asyncio.to_thread(self.crypt_reader.page, index)
            if (not self.active_host or self.crypt_reader is not reader
                    or not self.workspace.accepts(token) or self.manager.active is not self):
                return
            self._show_crypt_content(kind, content)
            self.refresh_private_bookmarks()
            self.previous_page.enabled = index > 0
            self.next_page.enabled = index + 1 < len(reader.labels)
        except Exception as error:
            self.crypt_title.text = private_label('Cannot read page: ' + str(error)[:200])
        finally:
            self.crypt_read_page.enabled = True
            self.set_cloud_busy(False)

    def refresh_private_bookmarks(self):
        index = self.crypt_reader.labels.index(self.crypt_page.value)
        self.crypt_bookmark_selector.on_change = None
        self.crypt_bookmark_selector.items = ['Bookmarks…',
            *(self.crypt_reader.labels[i] for i in sorted(self.crypt_bookmarks))]
        self.crypt_bookmark_selector.value = 'Bookmarks…'
        self.crypt_bookmark_selector.on_change = self.select_private_bookmark
        self.crypt_bookmark_button.text = 'Unbookmark' if index in self.crypt_bookmarks else 'Bookmark'

    def toggle_private_bookmark(self, widget=None, **kwargs):
        if self.cloud_busy or self.crypt_reader is None or self.crypt_reader.editable:
            return
        index = self.crypt_reader.labels.index(self.crypt_page.value)
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
        if label in self.crypt_reader.labels:
            self.crypt_page.value = label
            self.loop.create_task(self.read_crypt_page())

    def swipe_crypt_page(self, direction):
        if self.crypt_reader is None or self.crypt_reader.editable:
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
        if self.crypt_reader is not None:
            await self.move_private_page(self.crypt_reader.labels.index(self.crypt_page.value) - 1)

    async def next_private_page(self, widget=None, **kwargs):
        if self.crypt_reader is not None:
            await self.move_private_page(self.crypt_reader.labels.index(self.crypt_page.value) + 1)

    def compact_private_view(self, view):
        from .action_menu import FeatureCommands
        old = view.crypt_view
        view.crypt_actions = toga.Button('•••', style=Pack(width=44, height=44))
        for control in (view.crypt_title, view.crypt_page, view.crypt_read_page, view.crypt_content, view.crypt_save):
            old.remove(control)
        view.crypt_tools_view = toga.ScrollContainer(horizontal=False, content=old, style=Pack(flex=1))
        old.add(toga.Button('Return to private document', on_press=self.resume_crypt, style=Pack(height=44)))
        if not view.crypt_reader.editable:
            old.insert(0, view.crypt_bookmark_button)
            old.insert(1, view.crypt_bookmark_selector)
            old.insert(2, toga.Label('Bookmarks stay in this session and are cleared on close.'))
        view.crypt_actions_menu = FeatureCommands(view.crypt_actions, self, [
            ('Open / Save As / Metadata…', self.show_private_tools), ('Fit comic page', self.fit_private_page),
            ('Close private document', self.close_crypt)], self.show_private_tools)
        view.crypt_title.style.flex = 1
        view.crypt_page.style.flex = 1
        view.crypt_title.style.font_size = 12
        controls = [toga.Box(children=[view.crypt_title, view.crypt_actions], style=Pack(direction=ROW))]
        if not view.crypt_reader.editable:
            controls.append(toga.Box(children=[view.crypt_page, view.crypt_read_page], style=Pack(direction=ROW)))
        controls.append(view.crypt_content)
        if view.crypt_reader.editable:
            view.crypt_save.text = 'Save'
            footer = toga.Box(children=[view.crypt_save], style=Pack(direction=ROW, margin_top=4))
            view.crypt_save.style.flex = 1
            if view.crypt_reader.kind in {'.md', '.markdown'}:
                view.crypt_preview_button = toga.Button('Preview', on_press=self.toggle_private_preview,
                                                       style=Pack(height=44, flex=1))
                footer.add(view.crypt_preview_button)
            controls.append(footer)
        if not view.crypt_reader.editable:
            header = toga.Box(children=controls[:2], style=Pack(direction=COLUMN))
            view.previous_page, view.next_page = page_buttons(self.previous_private_page, self.next_private_page)
            footer = toga.Box(children=[view.previous_page, view.next_page], style=Pack(direction=ROW))
            view.reading_frame = ReadingFrame(view.crypt_content, [header, footer], margin=12)
            view.crypt_view = view.reading_frame.widget
            view.crypt_controls = view.reading_frame.controls
            view.previous_page.enabled = False
            view.next_page.enabled = len(view.crypt_reader.labels) > 1
        else:
            view.crypt_view = toga.Box(children=controls, style=Pack(direction=COLUMN, margin=12, flex=1))
            view.crypt_controls = [control for control in controls if control is not view.crypt_content]
        view.crypt_immersive = view.crypt_reader.kind in {'.cbz', '.zip'}
        if view.crypt_immersive:
            view.reading_frame.set_immersive(True, comic=True)
        self.register_transfer_status(view.crypt_view)

    def toggle_private_reading_mode(self, widget=None, **kwargs):
        if self.crypt_reader is None or self.crypt_reader.kind not in {'.cbz', '.zip'}:
            return
        self.crypt_immersive = not self.crypt_immersive
        self.reading_frame.set_immersive(self.crypt_immersive, comic=True)
        self.refresh_transfer_status()
        self.resume_crypt()

    def clear_private_preview(self):
        preview = getattr(self, 'crypt_preview', None)
        if preview is not None:
            native = getattr(preview._impl, 'native', None)
            if native is not None:
                native.stopLoading()
            preview.set_content('https://logistics.invalid/closed/', '<p>Preview closed.</p>')
            if preview in self.crypt_content.children:
                self.crypt_content.remove(preview)
                self.crypt_content.add(self.crypt_text)
            self.crypt_preview_button.text = 'Preview'

    def toggle_private_preview(self, widget=None, **kwargs):
        if (self.cloud_busy and not getattr(self, 'transfer_busy', False)) or self.crypt_reader is None or not self.crypt_reader.editable:
            return
        preview = getattr(self, 'crypt_preview', None)
        if preview is not None and preview in self.crypt_content.children:
            self.clear_private_preview()
            return
        from .preview import markdown_preview
        from uuid import uuid4
        try:
            content = markdown_preview(self.crypt_text.value, int(self.preferences.values['font_size']))
        except ValueError as error:
            self.crypt_title.text = private_label(str(error))
            return
        if preview is None:
            self.crypt_preview = preview = toga.WebView(on_navigation_starting=lambda widget, url, **kw: False,
                                                       style=Pack(flex=1))
        preview.set_content('https://logistics.invalid/' + uuid4().hex + '/', content)
        self.crypt_content.remove(self.crypt_text)
        self.crypt_content.add(preview)
        self.crypt_preview_button.text = 'Edit'

    def show_private_tools(self, widget=None, **kwargs):
        if not self.cloud_busy:
            self.show_view(self.crypt_tools_view, destination='documents', route='private-tools', title='Private document actions')

    def fit_private_page(self, widget=None, **kwargs):
        self.crypt_image.fit_page()

    def close_crypt(self, widget=None, **kwargs):
        if not self.cloud_busy and self.clear_private_reader():
            self.show_cloud()
