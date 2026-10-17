"""Native PDF search controls; extraction runs outside the UI event loop."""
import asyncio
from threading import Event
import textwrap
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from features.pdf.search import Results, search_pdf, result_text


class PDFSearchBar(toga.Box):
    def __init__(self, document, *, on_page, alive):
        self.document, self.on_page, self.alive = document, on_page, alive
        self.results, self.cursor, self.query = Results(()), -1, None
        self.cancelled = Event()
        self.busy, self.disposed = False, False
        self.input = toga.TextInput(placeholder='Find in PDF…', on_confirm=self.next_match,
                                   on_change=self.changed, style=Pack(flex=1, height=44))
        self.previous = toga.Button('Previous match', on_press=self.previous_match, style=Pack(flex=1, height=44))
        self.following = toga.Button('Next match', on_press=self.next_match, style=Pack(flex=1, height=44))
        self.status = toga.Label('')
        super().__init__(children=[self.input,
            toga.Box(children=[self.previous, self.following], style=Pack(direction=ROW)), self.status],
            style=Pack(direction=COLUMN))

    def changed(self, widget=None, **kwargs):
        self.cancelled.set()
        self.results, self.cursor, self.query = Results(()), -1, None
        if hasattr(self, 'status'):
            self.status.text = ''

    async def next_match(self, widget=None, **kwargs):
        await self.find(1)

    async def previous_match(self, widget=None, **kwargs):
        await self.find(-1)

    async def find(self, direction):
        if self.disposed or self.busy or not self.alive():
            return
        query = ' '.join(self.input.value.split())
        if not query:
            self.changed()
            return
        self.busy = True
        self.previous.enabled = self.following.enabled = False
        try:
            if self.query != query:
                self.cancelled = Event()
                self.query = query
                self.status.text = 'Searching PDF…'
                results = await asyncio.to_thread(search_pdf, self.document.data, query, cancelled=self.cancelled.is_set)
                if self.disposed or self.cancelled.is_set() or not self.alive():
                    self.query = None
                    return
                self.results, self.cursor = results, -1 if direction > 0 else 0
            if self.results.matches:
                self.cursor = (self.cursor + direction) % len(self.results.matches)
                await self.on_page(self.results.matches[self.cursor].page)
            if not self.disposed and self.alive():
                self.status.text = textwrap.fill(result_text(self.results, self.cursor), width=35)
        except Exception as error:
            if not self.disposed and self.alive() and not self.cancelled.is_set():
                self.query = None
                self.status.text = textwrap.fill('Cannot search PDF: ' + str(error)[:200], width=35)
        finally:
            self.busy = False
            self.previous.enabled = self.following.enabled = not self.disposed

    def dispose(self):
        self.disposed = True
        self.cancelled.set()
        self.input.value = self.status.text = ''
        self.results, self.query, self.cursor = Results(()), None, -1
        self.document = None
        self.on_page, self.alive = None, lambda: False
