"""Provider-backed embedded source editing with the regular native CodeInput."""
import asyncio
import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from commonUtils.persistence.text import decode_bytes
from services.documents.storage import DocumentResource
from ..notes import MAX_NOTE
from ..preparation import PreparedDocument
from .preparation import read_prepared
from .library_tools import LibraryTools


class LibraryText(LibraryTools):
    kind = 'text'

    def __init__(self, library, path, snapshot, resource, prepared=None):
        self.library, self.path, self.snapshot, self.resource = library, path, snapshot, resource
        self.closed = self.busy = False
        self.mode_generation = 0
        self.text = snapshot.text
        self.view = toga.Box(style=Pack(direction=COLUMN, flex=1))
        self.source = self.formatted = None
        self.build_input(prepared)

    def build_input(self, prepared):
        self.view.add(self.source_input())

    @classmethod
    def preparation_inputs(cls, library, path):
        return {}

    @classmethod
    def prepare(cls, text, **inputs):
        return None

    @classmethod
    async def open(cls, library, path):
        epoch = library.epoch
        inputs = cls.preparation_inputs(library, path)
        def read_snapshot():
            result = PreparedDocument(path, cls.kind)
            try:
                result.resource = DocumentResource(library.provider, path, max_bytes=MAX_NOTE)
                data = result.resource.read(cancelled=lambda: not library.valid() or library.epoch != epoch)
                result.snapshot = decode_bytes(data, path=library.provider.root / path)
                result.rendered = cls.prepare(result.snapshot.text, **inputs)
                return result
            except BaseException:
                result.close()
                raise
        result = await read_prepared(read_snapshot)
        try:
            if not library.valid() or library.epoch != epoch:
                raise ValueError('Notes Library closed.')
            return cls(library, path, result.snapshot, result.resource, prepared=result.rendered)
        except BaseException:
            result.close()
            raise

    @property
    def dirty(self):
        return not self.closed and self.text != self.snapshot.text

    def changed(self, text):
        if self.closed or not self.library.valid():
            return
        self.text = text
        if hasattr(self, 'finder'):
            self.finder.document_changed()
        if self.library.session is not None:
            self.library.session.dirty = self.dirty
        self.library.notice.text = 'Unsaved changes' if self.dirty else ''

    def source_input(self):
        from commonUtils.ui.native.code_input import CodeInput
        if self.source is None:
            def changed(widget, **kwargs):
                if widget is self.source:
                    self.changed(widget.value)
            self.source = CodeInput(value=self.text, loop=self.library.host.loop, filename=self.path,
                readonly=not self.library.library.writable, on_change=changed, style=Pack(flex=1))
            self.library.host.presentation.bind_font(self.source, 'text')
        else:
            self.source.value = self.text
        return self.source

    async def choose_mode(self, formatted=False):
        return not self.closed and self.library.valid()

    async def show_find(self, widget=None, **kwargs):
        if not self.library.library.writable:
            self.library.notice.text = 'This file is read-only.'
            return
        return await super().show_find(widget, **kwargs)

    async def flush(self):
        # Native source controls publish changes synchronously through on_change.
        # Markdown overrides this for its asynchronous formatted WebView.
        return

    async def save(self, widget=None, **kwargs):
        if self.busy or self.closed or not self.library.valid() or not self.library.library.writable:
            return False
        self.busy = True
        try:
            await self.flush()
            if self.closed or not self.library.valid():
                return False
            if not self.dirty:
                return True
            text, snapshot = self.text, self.snapshot
            def write():
                data = snapshot.encode(text)
                self.resource.save(data, cancelled=lambda: self.closed or not self.library.valid())
                return decode_bytes(data, path=snapshot.path)
            saved = await asyncio.to_thread(write)
            if self.closed or not self.library.valid():
                return False
            self.snapshot = saved
            self.library.refresh_library_indexes()
            await self.flush()
            if self.closed or not self.library.valid():
                return False
            self.changed(self.text)
            return not self.dirty
        except (OSError, ValueError) as error:
            self.library.notice.text = str(error)
            return False
        finally:
            self.busy = False

    def dispose(self):
        if self.closed:
            return
        self.closed = True
        self.retire_tools()
        self.view.clear()
        if self.formatted is not None:
            self.formatted.dispose()
        self.resource.close()
        if self.source is not None:
            self.source.dispose()
            self.source.value = ''
            self.source = None
        self.text = ''
        self.snapshot = None
