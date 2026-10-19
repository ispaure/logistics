"""PDF destinations presented with the same hierarchy as EPUB and help."""
import asyncio
import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from commonUtils.ui.native.presentation import HierarchyList


class PDFContents(toga.Box):
    def __init__(self, document, *, on_page, alive, row_style=None):
        self.document, self.on_page, self.alive = document, on_page, alive
        self.row_style, self.tree, self.busy = row_style, None, False
        self.button = toga.Button('Document contents', on_press=self.toggle, style=Pack(height=48))
        self.notice = toga.Label('')
        super().__init__(children=[self.button, self.notice], style=Pack(direction=COLUMN))

    async def toggle(self, widget=None, **kwargs):
        if self.busy or not self.alive():
            return
        if self.tree is None:
            from features.pdf.contents import contents
            self.busy, self.button.enabled = True, False
            self.notice.text = 'Loading contents…'
            try:
                entries = await asyncio.to_thread(contents, self.document.data)
                if not self.alive():
                    return
                if not entries:
                    self.notice.text = 'This PDF has no contents. Use the page number or search.'
                    return
                self.tree = HierarchyList(entries, self.choose, row_style=self.row_style)
                self.scroller = toga.ScrollContainer(content=self.tree.rows, horizontal=False,
                                                     style=Pack(height=240))
                self.notice.text = ''
            except Exception:
                if self.alive():
                    self.notice.text = 'Contents could not be read. Use the page number or search.'
                return
            finally:
                self.busy, self.button.enabled = False, True
        if self.scroller in self.children:
            self.remove(self.scroller)
            self.button.text = 'Document contents'
        else:
            self.add(self.scroller)
            self.button.text = 'Hide document contents'

    def choose(self, entry):
        if self.alive():
            self.tree.selected = lambda candidate: candidate == entry
            self.tree.render()
            if self.scroller in self.children:
                self.remove(self.scroller)
            self.button.text = 'Document contents'
            return self.on_page(entry.index)

    def dispose(self):
        self.alive = lambda: False
        self.document = self.on_page = None
        if self.tree is not None:
            self.tree.entries.clear()
            self.tree.collapsed.clear()
            self.tree.rows.clear()
            self.tree.selected = self.tree.choose = None
        self.notice.text = ''
        self.button.enabled = False
        self.clear()
