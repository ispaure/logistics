"""Track layout-independent text progress and native screen-page counts."""
import asyncio
from itertools import accumulate
import json
from uuid import uuid4
from weakref import ref

from features.books.locations import ChapterText, LayoutPages
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
        self.text_lengths = [None] * len(book.spine)
        self.text_starts = None
        self.text_offset = 0
        self.text_scan = None
        self.text_error = False
        self.bridge = self.view = self.render = self.loop = None
        self.chapter = self.page = 0
        self.columns = 1
        self.error = False
        from services.documents.page_visits import PageVisits
        self.visits = PageVisits()

    @property
    def book(self):
        return self.book_ref()

    def bind(self, view, chapter, render, loop, *, length=None, worker=False):
        self.cancel()
        self.view, self.bridge, self.chapter = view, view._chapter_bridge, chapter
        self.render, self.loop = render, loop
        self.page, self.columns = 0, 1
        self.text_offset = self.bridge.offset
        if length is not None:
            self.text_lengths[chapter] = length
        if self.text_starts is None and not self.text_error:
            self.text_scan = loop.create_task(self.scan_text(render, worker))
        self.worker = worker
        self.bridge.on_pagination = self.receive
        self.bridge.pagination_cleanup = self.cancel
        if self.bridge.pagination_state is not None:
            self.receive(self.bridge.pagination_state)
        else:
            self.publish()

    def cancel(self):
        if self.text_scan is not None:
            self.text_scan.cancel()
            self.text_scan = None
        if self.bridge is not None:
            self.bridge.on_pagination = None
            self.bridge.pagination_cleanup = None
            task = self.bridge.pagination_task
            if task is not None:
                task.cancel()
                self.bridge.pagination_task = None
        self.bridge = self.view = self.render = None

    async def scan_text(self, render, worker):
        try:
            # Let the opening chapter paint before walking the rest of the book.
            await asyncio.sleep(.15)
            def length(index):
                return ChapterText(render(index)).length
            for index, known in enumerate(self.text_lengths):
                if known is None:
                    if worker:
                        self.text_lengths[index] = await asyncio.to_thread(length, index)
                    else:
                        # A private bridge can retire synchronously between chapters.
                        await asyncio.sleep(.001)
                        self.text_lengths[index] = length(index)
            self.text_starts = tuple(accumulate(self.text_lengths, initial=0))
        except (OSError, ValueError):
            self.text_error = True
        self.publish()

    def receive(self, value):
        if self.bridge is None or self.bridge.closed:
            return
        changed = self.pages.reset(value['layout'])
        self.page, self.columns = value['index'], value['columns']
        self.text_offset = self.bridge.offset
        if changed:
            self.visits.previous.clear()
            self.visits.current = (self.chapter, self.page)
        else:
            self.visits.visit((self.chapter, self.page))
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
        value = self.pages.position(self.chapter, self.page, self.columns, include_percent=False)
        if self.error:
            value['text'] = f'Page count unavailable · Chapter {self.chapter + 1} of {len(self.pages.counts)}'
            value['mobile'] = value['text'].replace(' · ', '\n')
        if self.text_starts and self.text_starts[-1]:
            offset = min(max(0, self.text_offset), self.text_lengths[self.chapter])
            percent = (self.text_starts[self.chapter] + offset) * 100 // self.text_starts[-1]
            for key in ('text', 'mobile'):
                value[key] = f'{percent}% · {value[key]}'
        self.changed(value)

    def text_position(self, offset):
        if offset != self.text_offset:
            self.text_offset = offset
            self.publish()

    async def count(self, bridge, layout):
        try:
            # Rotation often sends several intermediate viewport sizes.
            await asyncio.sleep(.15)
            if self.text_scan is not None:
                await asyncio.shield(self.text_scan)
            for index in range(len(self.pages.counts)):
                if bridge is not self.bridge or bridge.closed or layout != self.pages.layout:
                    return
                if self.pages.counts[index] is not None:
                    continue
                # Only ordinary imports can retain chapter data in a worker
                # after the owning bridge has been disposed.
                content = await asyncio.to_thread(self.render, index) if self.worker else self.render(index)
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
            # Native page events arrive asynchronously after JS execution.
            # Keep Back in restore mode until the requested page is published.
            for _ in range(50):
                if self.chapter != chapter or self.bridge is None or self.bridge.closed:
                    return
                if self.page == page:
                    return
                await asyncio.sleep(.01)
