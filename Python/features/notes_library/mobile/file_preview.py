"""Read-only files stay in the library article pane and its document lifetime."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from services.documents.mobile_views import retire_webview
from commonUtils.ui.native.inline_html import set_inline_html
from services.documents.file_preview import FilePreview
from ..preparation import PreparedDocument
from .preparation import read_prepared


class LibraryFilePreview:
    kind = 'file'
    dirty = False

    def __init__(self, library, preview, html):
        self.library, self.preview, self.index = library, preview, 0
        self.path, self.closed, self.busy = preview.path, False, False
        self.web = library.access.webview(style=Pack(flex=1), max_bytes=48 * 1024 * 1024)
        self.pdf = None
        self.previous = toga.Button('Previous page', on_press=lambda widget: self.turn(-1))
        self.following = toga.Button('Next page', on_press=lambda widget: self.turn(1))
        self.label = toga.Label('')
        self.view = toga.Box(style=Pack(direction=COLUMN, flex=1))
        if preview.count > 1:
            self.view.add(toga.Box(children=[self.previous, self.label, self.following], style=Pack(direction=ROW)))
        self.view.add(self.web)
        try:
            if preview.document is None:
                self.publish(html)
            else:
                from features.pdf.mobile.continuous import PDFScroll
                ratios, first = html
                self.pdf = PDFScroll(self.web, preview.document, ratios, loop=library.host.loop,
                                     active=self.active, on_position=self.position)
                self.pdf.jump(0, first)
                self.position(0, None)
        except BaseException:
            self.dispose()
            raise

    @classmethod
    async def open(cls, library, path):
        epoch = library.epoch
        cancelled = lambda: not library.valid() or library.epoch != epoch
        def read():
            result = PreparedDocument(path, None)
            try:
                result.preview = FilePreview.open(library.provider, path, cancelled=cancelled)
                if result.preview.document is None:
                    result.rendered = result.preview.page()
                else:
                    from features.pdf.mobile.continuous import page_ratios, render_page
                    document = result.preview.document
                    result.rendered = page_ratios(document, cancelled=cancelled), render_page(document, 0)
                return result
            except BaseException:
                result.close()
                raise
        result = await read_prepared(read)
        try:
            if cancelled():
                raise ValueError('Notes Library closed.')
            return cls(library, result.preview, result.rendered)
        except BaseException:
            result.close()
            raise

    def active(self):
        return (not self.closed and self.library.valid() and self.library.embedded is self
                and self.view.parent is not None)

    def publish(self, html):
        self.library.access.validate_preview(html, 48 * 1024 * 1024)
        set_inline_html(self.web, 'https://library-file.invalid/', html)

    def position(self, index, location):
        if index != self.index or not self.label.text:
            self.index = index
            self.label.text = f'Page {index + 1} of {self.preview.count}'
            self.previous.enabled = index > 0
            self.following.enabled = index + 1 < self.preview.count

    async def turn(self, direction):
        if self.pdf is not None and self.active():
            index = self.index + direction
            if 0 <= index < self.preview.count:
                self.pdf.jump(index, None, {'zoom': (self.pdf.location or {}).get('zoom', 1)})
                self.position(index, None)

    async def flush(self):
        return

    def dispose(self):
        if self.closed:
            return
        self.closed = True
        if self.pdf is not None:
            self.pdf.dispose()
        else:
            retire_webview(self.web)
        self.view.clear()
        self.preview.close()
