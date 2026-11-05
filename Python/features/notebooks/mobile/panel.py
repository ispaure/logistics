"""Installed Android/iOS notebook library and offline canvas workflow."""
import asyncio
import json
import sys
from io import BytesIO
from pathlib import Path
from services.documents.storage import read_local_bytes
import toga
from commonUtils.ui.native.inline_html import set_inline_html
from commonUtils.ui.native.text_size import native_backend
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from ..notebook import Notebook, MAX_ARCHIVE
from ..recovery import Repository
from ..editor import Editor
from ..bridge import Bridge, RetiredCanvas
from ..protocol import document_state, stroke_script, ink_patch_script, update_script, validate_action
from .surface import mobile_editor_html


class NotebookResponseTimeout(TimeoutError):
    """Only a response-only JavaScript wait exceeded its deadline."""


def _input_true(value):
    # Pinned Rubicon maps NSNumber BOOL encoded as char to Python int0/int1.
    return value is True or type(value) is int and value == 1


def _consume_input_result(future):
    try:
        future.result()
    except BaseException:
        pass


async def _bounded_input_result(awaitable, timeout):
    # Never cancel Toga's native JavaScript future: a late UIKit completion may
    # still arrive. Retain only its exception consumer after our bounded wait.
    query = asyncio.ensure_future(awaitable)
    try:
        done, _ = await asyncio.wait((query,), timeout=max(0, timeout))
        if not done:
            raise TimeoutError('Finishing pen input. Try again after the current stroke is saved.')
        return query.result()
    finally:
        if not query.done():
            query.add_done_callback(_consume_input_result)


class NotebookPanel:
    def __init__(self, app, *, library=True):
        self.app = app
        self._repository = None
        self.document = None
        self.privacy_gate = None
        self.editor = None
        self.web = None
        self.boox_refresh = None
        self.pen_input = None
        self.pencil_hover = None
        self.pencil_input_trace = None
        self.key = None
        self.busy = False
        self.closed = False
        self.view = toga.Box(style=Pack(direction=COLUMN, flex=1))
        from services.documents.mobile_notebooks import install_notebook_controls
        install_notebook_controls(self)
        self._release_protection = app.protection.register(self, self.privacy_gates)
        if library:
            self.library()
        else:
            self.status = toga.Label('')
            self.view.add(self.status)

    def privacy_gates(self):
        return (self.privacy_gate,)

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
        if self.busy or self.closed or not self.app.active_host:
            return False
        from .setup import choose_new_notebook
        generation = getattr(self.app, 'navigation_generation', None)
        self.busy = True
        try:
            book = await choose_new_notebook(self.app)
        finally:
            self.busy = False
        if generation != getattr(self.app, 'navigation_generation', None):
            return False
        if book is None or self.closed or not self.app.active_host:
            return False
        return await self.load(lambda: book)

    async def load(self, read, key=None, *, mount=True):
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
            self.open(book, key, mount=mount)
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

    def open_resource(self, document, *, mount=True):
        self.document = document
        self.open(document.book, document.key, mount=mount)

    def state(self):
        state = document_state(self.editor, self.document)
        state['native_close'] = hasattr(self.view, '_native_reader_buttons')
        state['native_actions'] = hasattr(self, 'native_actions')
        state['native_pen'] = self.pen_input is not None and bool(getattr(self.pen_input, 'enabled', True))
        if self.pen_input is not None and isinstance(getattr(self.pen_input, 'view_id', None), str):
            state['native_pen_nonce'] = self.pen_input.view_id
        state['frame_batched_ink'] = sys.platform == 'ios'
        from .viewport import tablet_viewport
        state['tablet'] = tablet_viewport(self.web)
        return state

    @property
    def native_transport(self):
        return getattr(self.pen_input, 'owns_native_transport', False) is True

    @property
    def native_input_pending(self):
        return self.native_transport and bool(self.pen_input.pending)

    async def flush_input(self, *, timeout=4):
        """Lifecycle barrier only; never called from a busy JS command."""
        web, canvas = self.web, self.bridge
        if web is None or not native_backend(web).startswith(('toga_iOS.', 'toga_android.')):
            return
        deadline = asyncio.get_running_loop().time() + timeout
        for _ in range(200):
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError('Finishing pen input. Try again after the current stroke is saved.')
            if self.closed or self.web is not web or self.bridge is not canvas or not canvas.active:
                raise ValueError('The notebook canvas is no longer active.')
            if not self.native_input_pending:
                try:
                    idle = await _bounded_input_result(web.evaluate_javascript('window.notebookIdle?.() === true'), remaining)
                except TimeoutError:
                    raise
                except Exception as error:
                    raise ValueError('Notebook input is unavailable; your draft remains open.') from error
                if _input_true(idle) and not self.native_input_pending and not self.busy:
                    return
            await asyncio.sleep(min(.02, remaining))
        raise TimeoutError('Finishing pen input. Try again after the current stroke is saved.')

    async def save_from_view(self, *, timeout=4):
        """Host Save enters the JS queue; it never manufactures an action ACK."""
        await self.flush_input(timeout=timeout)
        web, canvas = self.web, self.bridge
        if web is None or self.closed or not canvas.active:
            raise ValueError('The notebook canvas is unavailable; your draft remains open.')
        admitted = await _bounded_input_result(web.evaluate_javascript("""(()=>{
            if(typeof window.notebookIdle!=='function' || !window.notebookIdle() ||
               typeof window.notebookNativeAction!=='function')return false;
            window.notebookNativeAction('save');
            return queue[0]?.op==='save';
        })()"""), timeout)
        if not _input_true(admitted):
            raise ValueError('Finish the current stroke and try Save again. Your draft remains open.')
        if self.closed or self.web is not web or self.bridge is not canvas or not canvas.active:
            raise ValueError('The notebook canvas changed during Save; your draft remains open.')
        # This waits on native/JS idle only. The separately dispatched Save
        # worker is never cancelled if admission/completion remains unconfirmed.
        await self.flush_input(timeout=timeout)
        if self.closed or self.web is not web or self.bridge is not canvas or not canvas.active:
            raise ValueError('The notebook canvas changed during Save; your draft remains open.')
        return self.document is not None and not self.document.dirty and not self.native_input_pending and not self.busy

    def open(self, book, key, *, mount=True):
        if self.document is not None and self.document.book is not book:
            if self.document.recovery is not None:
                self._repository = self.document.recovery
            self.document.close()
            self.document = None
        self.key = key
        self.editor = Editor(book, self.document.checkpoint if self.document else lambda book: self.repository.save(key, book))
        if mount:
            self.mount_canvas()

    def mount_canvas(self):
        self.retire_canvas()
        self.bridge = Bridge()
        from services.documents.mobile_views import document_webview
        resource = self.document.resource if self.document else None
        self.web = document_webview(resource, on_navigation_starting=self.navigate,
                                    on_webview_load=self.canvas_loaded, style=Pack(flex=1))
        self._fold_subscription = self.app.presentation.register_layout(('notebook-fold', id(self)), self,
            lambda owner, frame: owner.refresh_fold())
        self._fold_signature = ()
        self._canvas_ready = False
        if native_backend(self.web).startswith('toga_android.'):
            from java import jclass
            self.boox_refresh = jclass('io.github.ispaure.logistics.notebooks.BooxRefresh').attach(self.web._impl.native)
            self.pen_input = jclass('io.github.ispaure.logistics.notebooks.NotebookInput').attach(
                self.web._impl.native, self.boox_refresh)
        from .ios_input import attach
        self.pencil_hover = attach(self.web)
        location = getattr(self.view, '_document_location_row', None)
        restore_location = location is not None and location.parent is self.view
        header = getattr(self.view, '_document_title_header', None)
        for child in list(self.view.children):
            if child is not header:
                self.view.remove(child)
        self.view.add(self.web)
        if restore_location:
            self.view.insert(0, location)
        if native_backend(self.web).startswith('toga_iOS.'):
            from .ios_native_pen import attach as attach_native_pen
            self.pen_input = attach_native_pen(self.web, window=self.app.main_window._impl.native,
                window_owner=self.app.main_window)
            if self.pen_input is not None:
                self.pen_input.start_reporting(self.app.loop, Path(self.app.private_root) / 'notebook-input-diagnostics.json')
            if self.pen_input is None:
                # The compiled producer never installs a Python contact observer.
                # Ordinary DOM fallback retains its existing paired diagnostics.
                from .ios_input import attach_diagnostics
                self.pencil_input_trace = attach_diagnostics(self.web, self.app.loop,
                    Path(self.app.private_root) / 'notebook-input-diagnostics.json')
        set_inline_html(self.web, 'https://logistics.invalid/notebooks/', mobile_editor_html(
            self.state(), self.bridge.url, stylesheet=self.app.presentation.css_variables(),
            paper_preview=self.app.preferences.values.get('notebook_paper_preview', 'true') == 'true'))

    async def canvas_loaded(self, widget=None, **kwargs):
        if widget is not self.web:
            return
        self._canvas_ready = True
        self._fold_signature = ()
        self.refresh_fold()

    def refresh_fold(self):
        if self.web is None or not getattr(self, '_canvas_ready', False) or getattr(self, '_fold_pending', None) is not None:
            return
        web = self.web
        async def update():
            try:
                region = self.app.presentation.fold_division(web)
                geometry = None
                if region is not None and not region.vertical:
                    height = float(web._impl.native.bounds.size.height)
                    geometry = [region.y / height, (region.y + region.height) / height]
                signature = tuple(geometry) if geometry else None
                if self.web is web and signature != self._fold_signature:
                    await web.evaluate_javascript('window.notebookFold?.(' + json.dumps(geometry) + ')')
                    if self.web is web:
                        self._fold_signature = signature
            finally:
                if getattr(self, '_fold_pending', None) is asyncio.current_task():
                    self._fold_pending = None
        self._fold_pending = self.app.loop.create_task(update())

    def navigate(self, widget, url, **kwargs):
        if self.busy or self.closed or not self.app.active_host or widget is not self.web:
            return False
        action = self.bridge.command(url)
        if action is not None:
            self.busy = True
            self.app.loop.create_task(self.perform(action, canvas=self.bridge))
        return False

    async def _respond(self, web, script, canvas, *, timeout=4, release_busy=True):
        """A response-only wait follows completed worker work, never an active write."""
        if release_busy:
            self.busy = False
        try:
            result = await _bounded_input_result(web.evaluate_javascript(script), timeout)
        except TimeoutError as error:
            raise NotebookResponseTimeout(str(error)) from error
        if canvas is not self.bridge or not canvas.active or self.closed or self.web is not web:
            raise RetiredCanvas()
        return result

    def _native_notice(self, message):
        status = getattr(self, 'status', None)
        if status is not None:
            status.text = message
            self.view._native_reader_status = status
            render = getattr(getattr(self.app, 'adaptive', None), 'render', None)
            if render is not None:
                render()

    def _response_unavailable(self):
        # Do not retry an ACK: JS may have executed while its completion stalled.
        self._native_notice('Could not update the notebook display. Your draft is retained; Close can save or discard it.')

    async def perform(self, action, *, canvas=None):
        canvas = canvas or self.bridge
        if canvas is not self.bridge or not canvas.active:
            return
        self.busy = True
        error = ''
        web, editor = self.web, self.editor
        previous_ink = list(editor.notebook.page(editor.index).strokes) if action.get('op') == 'erase' else None
        ack_dispatched = False
        async def respond(script, *, acknowledges=False, release_busy=True):
            nonlocal ack_dispatched
            if acknowledges:
                ack_dispatched = True
            return await self._respond(web, script, canvas, release_busy=release_busy)
        try:
            op = validate_action(action)
            if op in {'save', 'save-as', 'export'} and self.native_transport:
                pending = self.native_input_pending
                if not pending:
                    try:
                        pending = await canvas.wait(_bounded_input_result(web.evaluate_javascript(
                            'queue.slice(1).some(action => action.op === "stroke" || action.op === "erase")'), 1))
                    except Exception:
                        pending = True
                if _input_true(pending) or self.native_input_pending:
                    # A non-error ack preserves queued strokes; notebookUpdate's
                    # error path clears the queue and must not be used here.
                    self.busy = False
                    script = update_script(self.state(), '') + ";document.getElementById('status').textContent='Finishing pen input; try again.'"
                    await respond(script, acknowledges=True)
                    return
            if op == 'page-previews':
                from ..previews import page_previews
                previews = await canvas.wait(asyncio.to_thread(page_previews, editor.notebook, action['start']))
                await respond('window.notebookPagePreviews(' + json.dumps(previews) + ')')
            if op == 'library':
                # Release the JS queue before native guards. Cancel/Keep editing
                # must leave a usable canvas, and queued ink precedes this action.
                self.busy = False
                await respond(update_script(self.state(), ''), acknowledges=True)
            if op == 'document-location':
                from services.documents.mobile_notebooks import notebook_location
                window = self.view.window
                location = notebook_location(self)
                if window is not None and location:
                    await canvas.wait(window.dialog(toga.InfoDialog('Document location', location)))
            if op == 'show-in-folder':
                self.busy = True
                from services.documents.mobile_notebooks import show_notebook_in_folder
                await canvas.wait(show_notebook_in_folder(self))
            if op == 'delete-file':
                self.busy = True
                await canvas.wait(self.delete_document())
            if op == 'library':
                if hasattr(self, 'session'):
                    # Match the other document editors: close with their normal
                    # save/discard guard, then return to the Home overview.
                    # The first ACK may already have dispatched a new worker.
                    self.app.__dict__.setdefault('_reader_returns', {})[self.session.id] = ('home', None, False)
                    self.app.request_reader_close(self.session.id)
                else:
                    self.library()
                return
            if op == 'delete-page':
                if not await canvas.wait(self.app.main_window.dialog(toga.ConfirmDialog(
                        'Delete this page?', 'This removes the current page. Undo is available.'))):
                    self.busy = False
                    await respond(update_script(self.state(), ''), acknowledges=True)
                    return
            if op == 'save':
                if self.document is not None and self.document.resource is not None:
                    await canvas.wait(asyncio.to_thread(self.document.save))
                else:
                    await respond(update_script(self.state(), ''), acknowledges=True)
                    picker = self.app.editor_picker()
                    await canvas.wait(picker.show_notebook_destination(self))
                    if getattr(self.document, 'source_unavailable', False):
                        picker.save_as_status.value = 'The original file is unavailable or changed. Choose a new location to save your retained draft.'
                    return
            elif op == 'save-as':
                await respond(update_script(self.state(), ''), acknowledges=True)
                await canvas.wait(self.app.editor_picker().show_notebook_destination(self))
                return
            elif op == 'transfer':
                if not await canvas.wait(self.confirm_export()):
                    await respond(update_script(self.state(), 'Cancelled.'), acknowledges=True)
                    return
                self.transfer_panel()
                return
            elif op == 'export':
                if not await canvas.wait(self.confirm_export()):
                    await respond(update_script(self.state(), 'Cancelled.'), acknowledges=True)
                    return
                from commonUtils.ui.native.documents import export_stream
                from ..remarkable_export import export_rmdoc
                data = await canvas.wait(asyncio.to_thread(export_rmdoc, editor.notebook))
                name = editor.notebook.name.replace('/', '-').replace('\\', '-') + '.rmdoc'
                saved = await canvas.wait(export_stream(self.app, name, lambda: BytesIO(data)))
                if not saved:
                    error = 'Export cancelled. Your notebook remains open.'
            elif op not in {'save', 'save-as', 'show-in-folder', 'document-location', 'delete-file', 'page-previews'}:
                await canvas.wait(asyncio.to_thread(editor.apply, action))
                if hasattr(self, 'session') and op == 'rename':
                    self.session.title = editor.notebook.name
                    self.app.refresh_document_list()
                    self.app.adaptive.render()
        except asyncio.CancelledError:
            if (canvas is self.bridge and canvas.active and not self.closed
                    and self.app.active_host and self.web is web and not ack_dispatched):
                try:
                    self.busy = False
                    ack_dispatched = True
                    message = ('Deletion interrupted. Retry Delete or use Save As.'
                               if action.get('op') == 'delete-file' else 'Action interrupted. Your notebook remains open.')
                    await asyncio.shield(_bounded_input_result(web.evaluate_javascript(update_script(self.state(), message)), 4))
                except (Exception, asyncio.CancelledError):
                    pass
            raise
        except RetiredCanvas:
            return
        except NotebookResponseTimeout:
            if canvas is not self.bridge or not canvas.active or self.closed or self.web is not web:
                return
            self._response_unavailable()
            if ack_dispatched:
                return
            # Page-preview callbacks do not acknowledge the action queue. Send
            # its one ordinary final ACK below; never duplicate an earlier ACK.
        except Exception as failure:
            error = str(failure)
        finally:
            # After its ACK, this action no longer owns a later queued worker.
            if canvas is self.bridge and not ack_dispatched:
                self.busy = False
        if canvas is not self.bridge or not canvas.active:
            return
        if hasattr(self, 'session') and self.document is not None:
            self.session.dirty = self.document.dirty
        if not self.closed and self.app.active_host and web in self.view.children:
            try:
                if action['op'] == 'stroke' and not error:
                    script = stroke_script(editor, self.document)
                elif action['op'] == 'erase' and not error:
                    script = ink_patch_script(editor, self.document, previous_ink)
                elif error and action['op'] in {'save', 'save-as', 'export'}:
                    # These operations do not mutate ink. An error ACK would
                    # clear strokes queued while their I/O was active.
                    label = 'Could not export: ' if action['op'] == 'export' else 'Save failed: '
                    message = label + error
                    self._native_notice(message)
                    status_script = 'document.getElementById("status").textContent=' + json.dumps(message)
                    if ack_dispatched:
                        # Save As already released its queue before the picker.
                        # Report the failure without consuming the next stroke
                        # or changing the busy state of its active worker.
                        await respond(status_script, release_busy=False)
                        return
                    script = update_script(self.state(), '') + ';' + status_script
                else:
                    script = update_script(self.state(), error)
                await respond(script, acknowledges=True)
            except RetiredCanvas:
                return
            except NotebookResponseTimeout:
                if (canvas is self.bridge and canvas.active and not self.closed and self.web is web
                        and not (error and action['op'] in {'save', 'save-as', 'export'})):
                    self._response_unavailable()
            except Exception as failure:
                if action['op'] in {'save', 'save-as', 'export'}:
                    # A failed display response cannot justify dropping ink
                    # queued during I/O. Keep the native error/Close path live.
                    if not error and not self.closed and self.web is web:
                        self._response_unavailable()
                    return
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
        from services.documents.mobile_notebooks import delete_notebook
        return await delete_notebook(self)

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
            location = getattr(self.view, '_document_location_row', None)
            if location is not None:
                self.view.insert(0, location)
            await self.web.evaluate_javascript(update_script(self.state()))
        box.add(toga.Button('Back to notebook', on_press=back, style=Pack(height=48, margin_top=16)))
        self.view.add(toga.ScrollContainer(content=box, horizontal=False, style=Pack(flex=1)))

    def retire_canvas(self):
        self._canvas_ready = False
        subscription = getattr(self, '_fold_subscription', None)
        if subscription is not None:
            subscription.dispose()
            self._fold_subscription = None
        pending = getattr(self, '_fold_pending', None)
        if pending is not None:
            pending.cancel()
            self._fold_pending = None
        bridge = getattr(self, 'bridge', None)
        if bridge is not None:
            bridge.retire()
        self.busy = False
        if self.pencil_input_trace is not None:
            self.pencil_input_trace.close()
            self.pencil_input_trace = None
        if self.pencil_hover is not None:
            self.pencil_hover.close()
            self.pencil_hover = None
        if self.pen_input is not None:
            self.pen_input.close()
            self.pen_input = None
        if self.boox_refresh is not None:
            self.boox_refresh.close()
            self.boox_refresh = None
        web = getattr(self, 'web', None)
        if web is not None:
            web.on_navigation_starting = None
            android = native_backend(web).startswith('toga_android.')
            private = callable(getattr(web, 'clear_private_content', None))
            # A retained panel must not retain its retired native WebView too.
            # Private retirement performs its own detach before clearing bytes.
            if not private and web.parent is not None:
                web.parent.remove(web)
            from services.documents.mobile_views import retire_webview
            retire_webview(web)
            if android and not private:
                # Blanking HTML alone leaves retired Chromium/GPU resources
                # alive across repeated notebook opens. Private views already
                # destroy their native view in clear_private_content().
                native = web._impl.native
                native.stopLoading()
                native.clearHistory()
                native.removeAllViews()
                native.destroy()
        self.web = None

    def dispose(self):
        self.closed = True
        native_actions = getattr(self, 'native_actions', None)
        if native_actions is not None:
            native_actions.dispose()
        self.retire_canvas()
        if self.document is not None:
            self.document.close()
            self.document = None
        self.editor = None
        self._release_protection()
