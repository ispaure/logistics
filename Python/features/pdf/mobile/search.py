"""Native PDF search controls; extraction runs outside the UI event loop."""
import asyncio
import textwrap
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from features.pdf.search import search_pdf
from features.pdf.search_controller import PDFSearchController, SearchRequest


class PDFSearchBar(toga.Box):
    def __init__(self, document, *, on_page, alive):
        self.document, self.on_page, self.alive = document, on_page, alive
        self.controller = PDFSearchController()
        self.navigating = False
        self.input = toga.TextInput(placeholder='Find in PDF…', on_confirm=self.next_match,
                                   on_change=self.changed, style=Pack(flex=1, height=44))
        self.previous = toga.Button('Previous match', on_press=self.previous_match, style=Pack(flex=1, height=44))
        self.following = toga.Button('Next match', on_press=self.next_match, style=Pack(flex=1, height=44))
        self.status = toga.Label('')
        super().__init__(children=[self.input,
            toga.Box(children=[self.previous, self.following], style=Pack(direction=ROW)), self.status],
            style=Pack(direction=COLUMN))

    def render(self):
        state = self.controller.state
        self.previous.enabled = state.previous_enabled and not self.navigating
        self.following.enabled = state.next_enabled and not self.navigating
        self.status.text = textwrap.fill(state.status, width=35)

    def changed(self, widget=None, **kwargs):
        self.controller.set_query(self.input.value)
        if hasattr(self, 'status'):
            self.render()

    async def next_match(self, widget=None, **kwargs):
        await self.find(1)

    async def previous_match(self, widget=None, **kwargs):
        await self.find(-1)

    async def find(self, direction):
        if self.controller.disposed or self.navigating or not self.alive():
            return
        self.controller.set_query(self.input.value)
        action = self.controller.step(direction)
        self.render()
        if isinstance(action, SearchRequest):
            worker = None
            try:
                worker = asyncio.create_task(asyncio.to_thread(
                    search_pdf, self.document.data, action.query,
                    cancelled=action.cancelled.is_set))
                results = await asyncio.shield(worker)
            except asyncio.CancelledError as error:
                action.cancelled.set()
                # Cancelling the await does not stop the extraction thread.
                # Retain the busy owner until that worker has retired.
                try:
                    if worker is not None:
                        await worker
                except Exception:
                    pass
                finally:
                    self.controller.fail(action, error)
                raise
            except Exception as error:
                if not self.alive():
                    action.cancelled.set()
                self.controller.fail(action, error)
                action = None
            else:
                if not self.alive():
                    action.cancelled.set()
                action = self.controller.complete(action, results)
            finally:
                self.render()
        if action is not None and not self.controller.disposed and self.alive():
            revision = self.controller.revision
            self.navigating = True
            self.render()
            try:
                await self.on_page(action.page)
            except Exception as error:
                if self.alive():
                    self.controller.navigation_failed(revision, error)
            finally:
                self.navigating = False
                self.render()

    def dispose(self):
        self.controller.dispose()
        self.input.value = ''
        self.render()
        self.document = None
        self.on_page, self.alive = None, lambda: False
