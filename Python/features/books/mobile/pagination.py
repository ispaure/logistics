"""Count inert chapters in the live reader's exact native column geometry."""
import asyncio
import json
from uuid import uuid4
from weakref import ref

from features.books.locations import LayoutPages
from .presentation import wait_chapter_ready


def chapter_renderer(book, values):
    from .content import chapter_html
    from .typography import options
    settings = dict(values)
    typography = options(settings)
    return lambda index: chapter_html(book, index, int(settings['epub_font_size']),
        margin=int(settings['reading_margin']), theme=settings['reading_theme'], links=True, **typography)


class MobilePagination:
    def __init__(self, book, changed):
        self.book_ref, self.changed = ref(book), changed
        self.pages = LayoutPages(len(book.spine))
        self.bridge = self.view = self.render = self.loop = None
        self.chapter = self.page = 0
        self.columns = 1
        self.error = False

    @property
    def book(self):
        return self.book_ref()

    def bind(self, view, chapter, render, loop):
        self.cancel()
        self.view, self.bridge, self.chapter = view, view._chapter_bridge, chapter
        self.render, self.loop = render, loop
        self.page, self.columns = 0, 1
        self.bridge.on_pagination = self.receive
        self.bridge.pagination_cleanup = self.cancel
        if self.bridge.pagination_state is not None:
            self.receive(self.bridge.pagination_state)
        else:
            self.publish()

    def cancel(self):
        if self.bridge is not None:
            self.bridge.on_pagination = None
            self.bridge.pagination_cleanup = None
            task = self.bridge.pagination_task
            if task is not None:
                task.cancel()
                self.bridge.pagination_task = None
        self.bridge = self.view = self.render = None

    def receive(self, value):
        if self.bridge is None or self.bridge.closed:
            return
        changed = self.pages.reset(value['layout'])
        self.page, self.columns = value['index'], value['columns']
        self.pages.record(self.chapter, value['count'])
        if changed:
            self.error = False
            if self.bridge.pagination_task is not None:
                self.bridge.pagination_task.cancel()
                self.bridge.pagination_task = None
        self.publish()
        task = self.bridge.pagination_task
        if not self.pages.complete and not self.error and (task is None or task.done()):
            self.bridge.pagination_task = self.loop.create_task(self.count(self.bridge, self.pages.layout))

    def publish(self):
        value = self.pages.position(self.chapter, self.page, self.columns)
        if self.error:
            value['text'] = f'Page count unavailable · Chapter {self.chapter + 1} of {len(self.pages.counts)}'
            value['mobile'] = value['text']
        self.changed(value)

    async def count(self, bridge, layout):
        try:
            # Rotation often sends several intermediate viewport sizes.
            await asyncio.sleep(.15)
            for index in range(len(self.pages.counts)):
                if bridge is not self.bridge or bridge.closed or layout != self.pages.layout:
                    return
                if self.pages.counts[index] is not None:
                    continue
                # Preparation is bounded by the chapter renderer and stays in
                # this owned UI task: no cancelled background worker can retain
                # private archive text after the reader's synchronous disposal.
                content = self.render(index)
                if bridge is not self.bridge or bridge.closed or layout != self.pages.layout:
                    return
                request = uuid4().hex
                await self.view.evaluate_javascript('window.reader && window.reader.measure(' +
                    json.dumps(content) + ',' + json.dumps(request) + ')')
                del content
                result = None
                async with asyncio.timeout(10):
                    while bridge is self.bridge and not bridge.closed and layout == self.pages.layout:
                        raw = await self.view.evaluate_javascript('JSON.stringify(window.reader && window.reader.measurement())')
                        value = json.loads(raw) if isinstance(raw, str) else None
                        if value and value.get('id') == request and value.get('done'):
                            result = value
                            break
                        await asyncio.sleep(.05)
                if not result or result.get('layout') != layout:
                    return
                if result.get('error'):
                    raise ValueError('Chapter page measurement failed')
                self.pages.record(index, result['count'])
                self.publish()
        except (OSError, ValueError, TimeoutError):
            if bridge is self.bridge and not bridge.closed and layout == self.pages.layout:
                self.error = True
                self.publish()

    async def seek_page(self, chapter, page):
        if chapter == self.chapter and self.view is not None and await wait_chapter_ready(self.view):
            await self.view.evaluate_javascript(f'window.reader && window.reader.seekPage({int(page)})')
