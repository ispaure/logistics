"""Read-only files stay in the library article pane and its document lifetime."""
import asyncio
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from services.documents.mobile_views import retire_webview
from commonUtils.ui.native.inline_html import set_inline_html
from ..file_preview import FilePreview


class LibraryFilePreview:
    kind = 'file'
    dirty = False

    def __init__(self, library, preview, html):
        self.library, self.preview, self.index = library, preview, 0
        self.path, self.closed, self.busy = preview.path, False, False
        self.web = library.access.webview(style=Pack(flex=1), max_bytes=48 * 1024 * 1024)
        self.previous = toga.Button('Previous page', on_press=lambda widget: self.turn(-1))
        self.following = toga.Button('Next page', on_press=lambda widget: self.turn(1))
        self.label = toga.Label('')
        self.view = toga.Box(style=Pack(direction=COLUMN, flex=1))
        if preview.count > 1:
            self.view.add(toga.Box(children=[self.previous, self.label, self.following], style=Pack(direction=ROW)))
        self.view.add(self.web)
        try:
            self.publish(html)
        except BaseException:
            self.dispose()
            raise

    @classmethod
    async def open(cls, library, path):
        epoch = library.epoch
        cancelled = lambda: not library.valid() or library.epoch != epoch
        def read():
            preview = FilePreview.open(library.provider, path, cancelled=cancelled)
            try:
                return preview, preview.page()
            except BaseException:
                preview.close()
                raise
        task = asyncio.create_task(asyncio.to_thread(read))
        try:
            preview, html = await asyncio.shield(task)
        except BaseException:
            def retire(finished):
                if not finished.cancelled() and finished.exception() is None:
                    finished.result()[0].close()
            task.add_done_callback(retire)
            raise
        try:
            if cancelled():
                raise ValueError('Notes Library closed.')
            return cls(library, preview, html)
        except BaseException:
            preview.close()
            raise

    def publish(self, html, *, index=None):
        self.library.access.validate_preview(html, 48 * 1024 * 1024)
        set_inline_html(self.web, 'https://library-file.invalid/', html)
        if index is not None:
            self.index = index
        self.label.text = f'Page {self.index + 1} of {self.preview.count}'
        self.previous.enabled = self.index > 0
        self.following.enabled = self.index + 1 < self.preview.count

    async def turn(self, direction):
        index = self.index + direction
        if self.closed or self.busy or not self.library.valid() or not 0 <= index < self.preview.count:
            return
        self.busy = True
        self.previous.enabled = self.following.enabled = False
        preview = self.preview
        task = asyncio.create_task(asyncio.to_thread(preview.page, index))
        try:
            html = await asyncio.shield(task)
            if not self.closed and self.library.valid():
                self.publish(html, index=index)
        except (OSError, ValueError) as error:
            if not self.closed and self.library.valid():
                self.library.notice.text = str(error)
        finally:
            if task.done():
                self.page_finished(task)
            else:
                task.add_done_callback(self.page_finished)

    def page_finished(self, task):
        if not task.cancelled():
            task.exception()  # Also consume a detached worker's rendering error.
        self.busy = False
        if self.closed:
            self.preview.close()
        elif self.library.valid():
            self.previous.enabled = self.index > 0
            self.following.enabled = self.index + 1 < self.preview.count

    async def flush(self):
        return

    def dispose(self):
        if self.closed:
            return
        self.closed = True
        retire_webview(self.web)
        self.view.clear()
        if not self.busy:
            self.preview.close()
