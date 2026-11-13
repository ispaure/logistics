"""Memory-only mobile PDF scrolling with one raster worker per surface."""
import asyncio
from base64 import b64encode
from json import dumps, loads
import logging
from math import isfinite

from commonUtils.ui.native.inline_html import set_inline_html
from commonUtils.ui.native.text_size import native_backend
from features.images.validation import image_dimensions

from .scroll_script import SHELL


def page_ratios(document, *, cancelled=lambda: False):
    from commonUtils.runtime.operations import check_cancelled
    ratios = []
    with document.open() as backend:
        for index in range(document.count):
            check_cancelled(cancelled)
            width, height = backend.page_size(index)
            ratio = width / height if height > 0 else 0
            ratios.append(max(.02, min(50, ratio)) if isfinite(ratio) and ratio > 0 else 1)
    return ratios


def render_page(document, index, *, links=False):
    # Opening a native backend captures its own input before rasterization.
    # A retired document can finish this render but cannot publish the result.
    data = document.data
    png = document.page(index)
    image_dimensions(png)
    if links:
        from features.pdf.links import safe_page_links
        annotations = safe_page_links(data, index)
    else:
        annotations = []
    return png, annotations


class PDFScroll:
    def __init__(self, view, document, ratios, *, loop, active, on_position,
                 on_action=None, on_image=None):
        self.view, self.document, self.loop = view, document, loop
        self.active, self.on_position = active, on_position
        self.on_action, self.on_image = on_action, on_image
        self.native = native_backend(view).startswith(('toga_iOS.', 'toga_android.'))
        self.revision = 0
        self.pending = None
        self.pages = {}
        self.task = None
        self.closed = self.suspended = False
        self.index = 0
        self.location = None
        self.magnifier = None
        self.applied_magnifier = None
        view.on_navigation_starting = lambda widget, url, **kwargs: False
        set_inline_html(view, 'https://pdf-view.invalid/', SHELL.replace('PAGE_RATIOS', dumps(ratios), 1))

    def jump(self, index, page, location=None):
        if self.closed:
            return
        self.suspended = False
        self.revision += 1
        self.index, self.location = index, location
        if page is not None:
            self.pages = {index: page}
        self.pending = index, location
        if self.on_image is not None and page is not None:
            self.on_image(page[0])
        if self.native and (self.task is None or self.task.done()):
            self.task = self.loop.create_task(self.run())

    def set_zoom(self, scale):
        if not self.closed and not self.suspended:
            self.revision += 1
            self.location = {**(self.location or {}), 'zoom': max(1, min(6, scale))}
            self.pending = self.index, self.location

    async def js(self, expression):
        # iOS returns an NSString proxy on some backend versions.
        result = await asyncio.wait_for(self.view.evaluate_javascript(expression), 2)
        return loads(str(result)) if result is not None else None

    async def run(self):
        try:
            while not self.closed:
                if not self.suspended and self.active():
                    try:
                        await self.update()
                    except (OSError, ValueError, RuntimeError, TimeoutError):
                        if not self.closed and not self.suspended:
                            logging.getLogger(__name__).debug('PDF viewport update failed', exc_info=True)
                await asyncio.sleep(.05)
        except asyncio.CancelledError:
            pass

    async def update(self):
        revision = self.revision
        if self.pending is not None:
            index, location = self.pending
            location = location or {}
            center = location.get('center', [])
            x = center[0] if isinstance(center, list) and center else .5
            zoom, offset = location.get('zoom', 1), location.get('offset', 0)
            def bounded(value, minimum, maximum, default):
                return value if type(value) in (int, float) and minimum <= value <= maximum else default
            args = [index, bounded(offset, 0, 1, 0), bounded(x, 0, 1, .5), bounded(zoom, 1, 6, 1), revision]
            ready = await self.js('JSON.stringify(window.pdf ? window.pdf.seek(...' + dumps(args) + ') : null)')
            if not ready or not self.current(revision):
                return
            self.pending = None
        state = await self.js('JSON.stringify(window.pdf ? window.pdf.state() : null)')
        if state is None or not self.current(revision) or state['revision'] != revision:
            return
        if self.magnifier != self.applied_magnifier:
            setting = self.magnifier
            await self.js('JSON.stringify(window.pdf?.magnifier(...' + dumps(setting) + ') || null)')
            if not self.current(revision):
                return
            self.applied_magnifier = setting
        if state['action'] is not None and self.on_action is not None:
            self.on_action(state['action'])
            if not self.current(revision):
                return
        index = state['page']
        changed = self.index != index
        self.index = index
        self.location = {'zoom': round(state['zoom'], 3), 'offset': round(state['offset'], 5),
                         'center': [round(state['x'], 5)]}
        self.on_position(index, self.location)
        if not self.current(revision):
            return
        wanted = state['wanted']
        self.pages = {i: page for i, page in self.pages.items() if i in wanted}
        if changed and self.on_image is not None:
            self.on_image(self.pages.get(index, (None,))[0])
        if state['missing']:
            target = state['missing'][0]
            if target not in self.pages:
                try:
                    page = await asyncio.to_thread(render_page, self.document, target, links=self.on_action is not None)
                except (OSError, ValueError, RuntimeError):
                    page = b'', []
                if not self.current(revision):
                    return
                self.pages[target] = page
                if target == self.index and self.on_image is not None:
                    self.on_image(page[0])
            png, links = self.pages[target]
            source = 'data:image/png;base64,' + b64encode(png).decode('ascii') if png else ''
            await self.js('JSON.stringify(window.pdf ? window.pdf.put(...' +
                          dumps([target, source, links, revision]) + ') : null)')

    def current(self, revision):
        return not self.closed and not self.suspended and self.active() and revision == self.revision

    def suspend(self):
        self.suspended = True
        self.revision += 1
        self.pages.clear()
        if self.native:
            self.view.evaluate_javascript(f'window.pdf && window.pdf.clear({self.revision})')
        if self.on_image is not None:
            self.on_image(None)

    def dispose(self):
        if self.closed:
            return
        self.closed = True
        self.pages.clear()
        self.pending = self.location = None
        if self.task is not None:
            self.task.cancel()
        self.document = self.on_position = self.on_action = self.on_image = None
        self.active = lambda: False
        from services.documents.mobile_views import retire_webview
        retire_webview(self.view)
