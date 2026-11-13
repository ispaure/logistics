"""Provider-backed embedded source editing with the regular native CodeInput."""
import asyncio
from threading import Event
import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from commonUtils.persistence.text import decode_bytes
from commonUtils.runtime.operations import OperationCancelled
from services.documents.storage import DocumentResource
from services.worker_retirement import drain_worker
from ..notes import MAX_NOTE
from ..preparation import PreparedDocument
from .preparation import read_prepared
from .library_tools import LibraryTools


class LibraryText(LibraryTools):
    kind = 'text'

    def __init__(self, library, path, snapshot, resource, prepared=None):
        self.library, self.path, self.snapshot, self.resource = library, path, snapshot, resource
        self.closed = self.busy = False
        self._save_worker = None
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
            cancel = Event()
            def cancelled():
                return cancel.is_set() or self.closed or not self.library.valid()
            def write():
                data = snapshot.encode(text)
                self.resource.save(data, cancelled=cancelled)
                return decode_bytes(data, path=snapshot.path)
            interruption = None
            worker = self._save_worker = asyncio.create_task(asyncio.to_thread(write))
            try:
                saved = await asyncio.shield(worker)
            except asyncio.CancelledError as error:
                interruption = error
                cancel.set()
                await drain_worker(worker)
                if worker.cancelled() or worker.exception() is not None:
                    raise
                saved = worker.result()
            finally:
                self._save_worker = None
                if self.closed:
                    self.resource.close()
            if self.closed or not self.library.valid():
                if interruption is not None:
                    raise interruption
                return False
            self.snapshot = saved
            self.library.refresh_library_indexes()
            if interruption is not None:
                # Save completed before cancellation reached the writer. Keep
                # newer input dirty against the bytes actually on disk.
                self.changed(self.text)
                raise interruption
            await self.flush()
            if self.closed or not self.library.valid():
                return False
            self.changed(self.text)
            return not self.dirty
        except (OSError, ValueError) as error:
            if not self.closed and self.library.valid():
                self.library.notice.text = str(error)
            return False
        except OperationCancelled:
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
        if self._save_worker is None:
            self.resource.close()
        if self.source is not None:
            self.source.dispose()
            self.source.value = ''
            self.source = None
        self.text = ''
        self.snapshot = None
