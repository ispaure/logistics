"""Installed Android/iOS notebook library and offline canvas workflow."""
import asyncio
from io import BytesIO
from pathlib import Path
from services.documents.storage import read_local_bytes
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from ..notebook import Notebook, MAX_ARCHIVE
from ..recovery import Repository
from ..editor import Editor
from ..bridge import Bridge, RetiredCanvas
from ..protocol import document_state, stroke_script, update_script, validate_action
from .surface import mobile_editor_html


class NotebookPanel:
    def __init__(self, app, *, library=True):
        self.app = app
        self._repository = None
        self.document = None
        self.privacy_gate = None
        self.editor = None
        self.web = None
        self.boox_refresh = None
        self.key = None
        self.busy = False
        self.closed = False
        self.view = toga.Box(style=Pack(direction=COLUMN, flex=1))
        if type(self.view._impl).__module__.startswith('toga_iOS.'):
            from mobile.control_icons import icon_button
            async def close(widget=None, **kwargs):
                if self.web is not None:
                    await self.web.evaluate_javascript("send({op:'library'})")
            self.view._reader_close_button = icon_button('close', 'Close document', on_press=close)
            self.view._native_reader_toolbar = toga.Box()
            self.view._native_reader_buttons = lambda: []
        if library:
            self.library()
        else:
            self.status = toga.Label('')
            self.view.add(self.status)

    @property
    def repository(self):
        if self.document is not None and self.document.recovery is not None:
            self._repository = self.document.recovery
        if self._repository is None:
            self._repository = Repository(Path(self.app.private_root) / 'notebooks')
        return self._repository

    def library(self):
        self.retire_canvas()
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
                await self.load(lambda: self.repository.open(key), key)
            box.add(toga.Button(name, on_press=reopen, style=Pack(margin_top=8, height=48)))
        self.view.add(toga.ScrollContainer(content=box, horizontal=False, style=Pack(flex=1)))

    async def new(self, widget=None, **kwargs):
        return await self.load(Notebook.new)

    async def load(self, read, key=None):
        if self.busy or self.closed or not self.app.active_host:
            return False
        self.busy = True
        try:
            book = await asyncio.to_thread(read)
            if self.closed or not self.app.active_host:
                return False
            if key is None:
                key = await asyncio.to_thread(self.repository.create, book)
            if self.closed or not self.app.active_host:
                return False
            if self.document is not None:
                if key == self.document.key:
                    self.document.book = book
                else:
                    self.document.close()
                    self.document = None
            self.open(book, key)
            return True
        except Exception as error:
            if not self.closed and self.app.active_host:
                self.library()
                self.status.text = str(error)
            return False
        finally:
            self.busy = False

    async def import_document(self, widget=None, **kwargs):
        from commonUtils.ui.native.documents import pick_document
        if self.busy or self.closed or not self.app.active_host:
            return
        self.busy = True
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
        except Exception as error:
            if not self.closed:
                self.status.text = str(error)
            return
        finally:
            self.busy = False
        await self.load(read)

    async def open_path(self, path):
        def read():
            return Notebook.read(read_local_bytes(path, max_bytes=MAX_ARCHIVE))
        return await self.load(read)

    def open_resource(self, document):
        self.document = document
        self.open(document.book, document.key)

    def state(self):
        state = document_state(self.editor, self.document)
        state['native_close'] = hasattr(self.view, '_native_reader_buttons')
        return state

    def open(self, book, key):
        if self.document is not None and self.document.book is not book:
            if self.document.recovery is not None:
                self._repository = self.document.recovery
            self.document.close()
            self.document = None
        self.key = key
        self.editor = Editor(book, self.document.checkpoint if self.document else lambda book: self.repository.save(key, book))
        self.mount_canvas()

    def mount_canvas(self):
        self.retire_canvas()
        self.bridge = Bridge()
        from services.documents.mobile_views import document_webview
        resource = self.document.resource if self.document else None
        self.web = document_webview(resource, on_navigation_starting=self.navigate, style=Pack(flex=1))
        if type(self.web._impl).__module__.startswith('toga_android.'):
            from java import jclass
            self.boox_refresh = jclass('io.github.ispaure.logistics.notebooks.BooxRefresh').attach(self.web._impl.native)
        self.web.set_content('https://logistics.invalid/notebooks/', mobile_editor_html(self.state(), self.bridge.url))
        for child in list(self.view.children):
            self.view.remove(child)
        self.view.add(self.web)

    def navigate(self, widget, url, **kwargs):
        if self.busy or self.closed or not self.app.active_host or widget is not self.web:
            return False
        action = self.bridge.command(url)
        if action is not None:
            self.busy = True
            self.app.loop.create_task(self.perform(action, canvas=self.bridge))
        return False

    async def perform(self, action, *, canvas=None):
        canvas = canvas or self.bridge
        if canvas is not self.bridge or not canvas.active:
            return
        self.busy = True
        error = ''
        web, editor = self.web, self.editor
        try:
            op = validate_action(action)
            if op == 'library':
                # Release the JS queue before native guards. Cancel/Keep editing
                # must leave a usable canvas, and queued ink precedes this action.
                self.busy = False
                await canvas.wait(web.evaluate_javascript(update_script(self.state(), '')))
            if op == 'show-in-folder':
                self.busy = True
                from mobile.document_sources import show_in_folder
                await canvas.wait(show_in_folder(self.app, self.session, self))
            if op == 'delete-file':
                self.busy = True
                await canvas.wait(self.delete_document())
            if op == 'library':
                if hasattr(self, 'session'):
                    # Match the other document editors: close with their normal
                    # save/discard guard, then return to the Home overview.
                    self.busy = False
                    self.app.__dict__.setdefault('_reader_returns', {})[self.session.id] = ('home', None, False)
                    self.app.request_reader_close(self.session.id)
                else:
                    self.library()
                return
            if op == 'delete-page':
                if not await canvas.wait(self.app.main_window.dialog(toga.ConfirmDialog(
                        'Delete this page?', 'This removes the current page. Undo is available.'))):
                    self.busy = False
                    await canvas.wait(web.evaluate_javascript(update_script(self.state(), '')))
                    return
            if op == 'save':
                if self.document is not None and self.document.resource is not None:
                    await canvas.wait(asyncio.to_thread(self.document.save))
                else:
                    await canvas.wait(web.evaluate_javascript(update_script(self.state(), '')))
                    await canvas.wait(self.app.editor_picker().show_notebook_destination(self))
                    return
            elif op == 'save-as':
                await canvas.wait(web.evaluate_javascript(update_script(self.state(), '')))
                await canvas.wait(self.app.editor_picker().show_notebook_destination(self))
                return
            elif op == 'transfer':
                if not await canvas.wait(self.confirm_export()):
                    await canvas.wait(web.evaluate_javascript(update_script(self.state(), 'Cancelled.')))
                    return
                self.transfer_panel()
                return
            elif op == 'export':
                if not await canvas.wait(self.confirm_export()):
                    await canvas.wait(web.evaluate_javascript(update_script(self.state(), 'Cancelled.')))
                    return
                from commonUtils.ui.native.documents import export_stream
                data = await canvas.wait(asyncio.to_thread(editor.notebook.to_bytes))
                name = editor.notebook.name.replace('/', '-').replace('\\', '-') + '.rmdoc'
                saved = await canvas.wait(export_stream(self.app, name, lambda: BytesIO(data)))
                if not saved:
                    error = 'Export cancelled. Your notebook remains open.'
            elif op not in {'save', 'save-as', 'show-in-folder', 'delete-file'}:
                await canvas.wait(asyncio.to_thread(editor.apply, action))
                if hasattr(self, 'session') and op == 'rename':
                    self.session.title = editor.notebook.name
                    self.app.refresh_document_list()
        except RetiredCanvas:
            return
        except Exception as failure:
            error = str(failure)
        finally:
            if canvas is self.bridge:
                self.busy = False
        if canvas is not self.bridge or not canvas.active:
            return
        if hasattr(self, 'session') and self.document is not None:
            self.session.dirty = self.document.dirty
        if not self.closed and self.app.active_host and web in self.view.children:
            try:
                if action['op'] == 'stroke' and not error:
                    script = stroke_script(editor, self.document)
                else:
                    script = update_script(self.state(), error)
                await web.evaluate_javascript(script)
            except Exception as failure:
                if not self.closed and self.web is web:
                    if self.document is not None and self.document.recovery is None:
                        self.retire_canvas()
                        for child in list(self.view.children):
                            self.view.remove(child)
                        self.status = toga.Label('Notebook draft retained. Reopen the canvas to resume: ' + str(failure))
                        self.view.add(self.status)
                        self.view.add(toga.Button('Resume notebook', on_press=lambda widget, **kw: self.open_resource(self.document)))
                    else:
                        self.library()
                        self.status.text = 'Notebook saved. Reopen it to resume: ' + str(failure)

    async def delete_document(self):
        from features.text_editor.mobile.document_dialogs import DocumentDialog
        document = self.document
        if document is None or not document.writable:
            raise ValueError('This notebook cannot be deleted.')
        if len(self.app.scene_manager.owners.hosts) > 1:
            raise ValueError('Close other app windows before deleting a document.')
        resource = document.resource
        warning = ('Permanently delete this notebook and its recovery draft? '
                   'Unsaved changes will also be removed.')
        if resource is not None:
            warning += ' The file will be deleted from its folder.'
        choice = await self.app.main_window.dialog(DocumentDialog(
            'Delete ' + document.book.name + '?', warning, delete=True))
        if choice != 'delete' or self.closed or self.document is not document or not self.app.active_host:
            return
        if len(self.app.scene_manager.owners.hosts) > 1:
            raise ValueError('Close other app windows before deleting a document.')
        def remove():
            if resource is not None:
                if resource.check()['revision'] != resource.revision:
                    raise ValueError('File changed; reopen it before deleting.')
                resource.provider.remove_empty(resource.path, resource.revision)
            if document.recovery is not None:
                import shutil
                from ..notebook import identifier
                shutil.rmtree(document.recovery.root / identifier(document.key))
        await asyncio.to_thread(remove)
        self.app.recent_documents.forget('notebook', self.session.resource)
        from mobile.resource_imports import ResourceImports
        imports = getattr(self.app, 'resource_imports', None) or ResourceImports(self.app.private_root)
        imports.forget('notebook', self.session.resource)
        self.busy = False
        self.app.__dict__.setdefault('_reader_returns', {})[self.session.id] = ('home', None, False)
        self.app.__dict__.setdefault('_reader_closing', set()).add(self.session.id)
        self.app.close_session(self.session.id, choice='discard')

    async def confirm_export(self):
        from services.documents.mobile_storage import confirm_export
        return await confirm_export(self.app, self.document.resource if self.document else None)

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
            if self.busy or self.closed:
                return
            self.view.remove(self.view.children[0])
            self.view.add(self.web)
            await self.web.evaluate_javascript(update_script(self.state()))
        box.add(toga.Button('Back to notebook', on_press=back, style=Pack(height=48, margin_top=16)))
        self.view.add(toga.ScrollContainer(content=box, horizontal=False, style=Pack(flex=1)))

    def retire_canvas(self):
        bridge = getattr(self, 'bridge', None)
        if bridge is not None:
            bridge.retire()
        self.busy = False
        if self.boox_refresh is not None:
            self.boox_refresh.close()
            self.boox_refresh = None
        web = getattr(self, 'web', None)
        if web is not None:
            web.on_navigation_starting = None
            from services.documents.mobile_views import retire_webview
            retire_webview(web)
        self.web = None

    def dispose(self):
        self.closed = True
        self.retire_canvas()
        if self.document is not None:
            self.document.close()
            self.document = None
        self.editor = None
