"""Installed Android/iOS notebook library and offline canvas workflow."""
import asyncio
from io import BytesIO
from pathlib import Path
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from ..notebook import Notebook, MAX_ARCHIVE
from ..workspace import Repository, Editor
from ..bridge import Bridge, update_script
from ..canvas import editor_html


class NotebookPanel:
    def __init__(self, app):
        self.app = app
        self.repository = Repository(Path(app.private_root) / 'notebooks')
        self.editor = None
        self.key = None
        self.busy = False
        self.closed = False
        self.view = toga.Box(style=Pack(direction=COLUMN, flex=1))
        self.library()

    def library(self):
        for child in list(self.view.children):
            self.view.remove(child)
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(toga.Label('Notebooks', style=Pack(font_size=24, font_weight='bold')))
        box.add(toga.Label('Editable reMarkable ink · originals stay untouched', style=Pack(margin_bottom=12)))
        self.status = toga.Label('', style=Pack(margin_bottom=8))
        box.add(self.status)
        box.add(toga.Box(children=[toga.Button('New notebook', on_press=self.new),
            toga.Button('Open .rmdoc…', on_press=self.import_document)], style=Pack(direction=ROW)))
        for key, name in self.repository.list():
            async def reopen(widget, key=key, **kwargs):
                try:
                    book = await asyncio.to_thread(self.repository.open, key)
                    self.open(book, key)
                except Exception as error:
                    self.status.text = str(error)
            box.add(toga.Button(name, on_press=reopen, style=Pack(margin_top=8, height=48)))
        self.view.add(toga.ScrollContainer(content=box, horizontal=False, style=Pack(flex=1)))

    async def new(self, widget=None, **kwargs):
        try:
            book = Notebook.new()
            key = await asyncio.to_thread(self.repository.create, book)
            self.open(book, key)
        except Exception as error:
            self.status.text = str(error)

    async def import_document(self, widget=None, **kwargs):
        from commonUtils.ui.native.documents import pick_document
        try:
            picked = await pick_document(self.app, title='Open reMarkable notebook')
            if picked is None:
                return
            adapter, reference = picked
            def read():
                with adapter.open(reference) as (name, stream):
                    if not name.lower().endswith('.rmdoc'):
                        raise ValueError('Choose an .rmdoc file.')
                    return Notebook.read(stream.read(MAX_ARCHIVE + 1))
            book = await asyncio.to_thread(read)
            key = await asyncio.to_thread(self.repository.create, book)
            self.open(book, key)
        except Exception as error:
            self.status.text = str(error)

    async def open_path(self, path):
        try:
            def read():
                with Path(path).open('rb') as stream:
                    return Notebook.read(stream.read(MAX_ARCHIVE + 1))
            book = await asyncio.to_thread(read)
            key = await asyncio.to_thread(self.repository.create, book)
            self.open(book, key)
        except Exception as error:
            self.library()
            self.status.text = str(error)

    def open(self, book, key):
        self.key = key
        self.editor = Editor(book, lambda book: self.repository.save(key, book))
        self.bridge = Bridge()
        self.web = toga.WebView(on_navigation_starting=self.navigate, style=Pack(flex=1))
        self.web.set_content('https://logistics.invalid/notebooks/', editor_html(self.editor.state(), self.bridge.url))
        for child in list(self.view.children):
            self.view.remove(child)
        self.view.add(self.web)

    def navigate(self, widget, url, **kwargs):
        action = self.bridge.command(url)
        if action is not None and not self.busy and not self.closed and self.app.active_host:
            self.app.loop.create_task(self.perform(action))
        return False

    async def perform(self, action):
        self.busy = True
        error = ''
        web, editor = self.web, self.editor
        try:
            op = action['op']
            if op == 'library':
                self.library()
                return
            if op == 'transfer':
                self.transfer_panel()
                return
            if op == 'export':
                from commonUtils.ui.native.documents import export_stream
                data = await asyncio.to_thread(editor.notebook.to_bytes)
                name = editor.notebook.name.replace('/', '-').replace('\\', '-') + '.rmdoc'
                saved = await export_stream(self.app, name, lambda: BytesIO(data))
                if not saved:
                    error = 'Export cancelled. Your notebook is saved on this device.'
            else:
                await asyncio.to_thread(editor.apply, action)
        except Exception as failure:
            error = str(failure)
        finally:
            self.busy = False
        if not self.closed and self.app.active_host and web in self.view.children:
            await web.evaluate_javascript(update_script(editor.state(), error))

    def transfer_panel(self):
        for child in list(self.view.children):
            self.view.remove(child)
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(toga.Label('Copy page to notebook', style=Pack(font_size=22)))
        box.add(toga.Label('The source page stays in this notebook.'))
        status = toga.Label('')
        box.add(status)
        for key, name in self.repository.list():
            if key == self.key:
                continue
            async def transfer(widget, key=key, **kwargs):
                if self.busy:
                    return
                self.busy = True
                try:
                    def copy_page():
                        target = self.repository.open(key)
                        target.copy_page(self.editor.notebook, self.editor.index)
                        self.repository.save(key, target)
                    await asyncio.to_thread(copy_page)
                    status.text = 'Page copied. Both notebooks are saved.'
                except Exception as error:
                    status.text = str(error)
                finally:
                    self.busy = False
            box.add(toga.Button(name, on_press=transfer, style=Pack(height=48, margin_top=8)))
        async def back(widget, **kwargs):
            self.view.remove(self.view.children[0])
            self.view.add(self.web)
            await self.web.evaluate_javascript(update_script(self.editor.state()))
        box.add(toga.Button('Back to notebook', on_press=back, style=Pack(height=48, margin_top=16)))
        self.view.add(toga.ScrollContainer(content=box, horizontal=False, style=Pack(flex=1)))

    def dispose(self):
        self.closed = True
        web = getattr(self, 'web', None)
        if web is not None:
            web.on_navigation_starting = None
            from features.text_editor.mobile.markdown_editor import retire_webview
            retire_webview(web)
        self.editor = None
