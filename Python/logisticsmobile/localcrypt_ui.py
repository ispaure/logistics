"""Native LocalCrypt reader/editor with no document/library persistence."""
import asyncio
import threading
import textwrap
import toga
from toga.style import Pack
from toga.style.pack import COLUMN

def private_label(value):
    # Native labels use their longest line as a minimum width. Bound messages
    # and virtual filenames so they cannot widen a phone's entire reader.
    return textwrap.fill(str(value), width=30)


from .localcrypt import LocalCryptCopies
from commonUtils.runtime.operations import check_cancelled


from .files_ui import FilesUI


class LocalCryptUI(FilesUI):
    def build_localcrypt(self):
        self.crypt_copies = LocalCryptCopies(self.private_root / 'LocalCrypt', self.cloud_client)
        self.crypt_reader = None
        self.crypt_metadata_fields = {}
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
        if hasattr(self, 'crypt_text'):
            self.crypt_text.value = ''
        if hasattr(self, 'crypt_image'):
            self.crypt_image.image = None
        if hasattr(self, 'crypt_page'):
            self.crypt_page.items = []
        if hasattr(self, 'crypt_title'):
            self.crypt_title.text = private_label('Encrypted copy closed')
        if hasattr(self, 'crypt_password'):
            self.crypt_password.value = ''
        return True

    def clear_private_catalog(self):
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

    async def open_crypt(self, widget=None, *, copies=None, key=None, prepared=None, **kwargs):
        copies = copies or self.crypt_copies
        key = key if key is not None else self.crypt_labels.get(self.crypt_selector.value)
        if self.cloud_busy or key is None:
            return
        password = self.crypt_password.value
        self.crypt_password.value = ''
        if self._crypt_cancel is not None:
            return
        if prepared is None and self.private_dirty():
            self.crypt_title.text = private_label('Unsaved changes: save, or discard and close.')
            self.resume_crypt()
            return
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
            view.crypt_text = toga.MultilineTextInput(readonly=not reader.editable, style=Pack(flex=1))
            view.crypt_image = toga.ImageView(style=Pack(flex=1))
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
        self.crypt_metadata_view = toga.ScrollContainer(content=toga.Box(children=children, style=Pack(direction=COLUMN, margin=12)), style=Pack(flex=1))
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
            kind, content = await asyncio.to_thread(self.crypt_reader.page, index)
            self._show_crypt_content(kind, content)
        except Exception as error:
            self.crypt_title.text = private_label('Cannot read page: ' + str(error)[:200])
        finally:
            self.crypt_read_page.enabled = True
            self.set_cloud_busy(False)

    def close_crypt(self, widget=None, **kwargs):
        if not self.cloud_busy and self.clear_private_reader():
            self.show_cloud()
