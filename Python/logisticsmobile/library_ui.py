"""Mobile Books and Comics catalogue; readers own their own presentation."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from commonUtils.ui.native.presentation import list_button


class LibraryCatalog:
    def build_library_catalog(self):
        self.library_search = toga.TextInput(placeholder='Search books and comics',
            on_change=self.filter_library, style=Pack(height=44, flex=1))
        self.library_rows = toga.Box(style=Pack(direction=COLUMN))
        self.library_records = []
        self.library_row_buttons = []
        self.library_view = toga.Box(children=[
            toga.Box(children=[self.library_search, self.book_import],
                     style=Pack(direction=ROW, margin_bottom=8)),
            toga.ScrollContainer(horizontal=False, content=self.library_rows, style=Pack(flex=1)),
            self.book_status], style=Pack(direction=COLUMN, margin=12, flex=1))
        self.book_import.text = 'Import…'
        self.book_import.style.width = 88
        self.book_status.style.font_size = 12


    def filter_library(self, widget=None, **kwargs):
        if not hasattr(self, 'library_rows'):
            return
        for child in list(self.library_rows.children):
            self.library_rows.remove(child)
        self.library_row_buttons = []
        query = self.library_search.value.casefold().strip()
        for record in self.library_records:
            if query and query not in record['name'].casefold():
                continue
            async def open_item(widget=None, resource=record['id'], **kw):
                if not self.book_busy:
                    await self.open_book(resource)
            button = toga.Button(record['name'], on_press=open_item,
                                 enabled=not self.book_busy, style=Pack(height=52))
            list_button(button)
            self.library_row_buttons.append(button)
            kind = 'EPUB' if record['kind'] == 'epub' else 'Comic'
            position = ('Chapter ' if record['kind'] == 'epub' else 'Page ') + str(record['position'] + 1)
            self.library_rows.add(toga.Box(children=[button,
                toga.Label(kind + ' · ' + position, style=Pack(font_size=12, margin_bottom=8))],
                style=Pack(direction=COLUMN, margin_bottom=4)))
        if not self.library_row_buttons:
            self.library_rows.add(toga.Label('No matching books.' if query else 'Import a book or comic to start reading.',
                                            style=Pack(margin_top=16)))


    def refresh_library(self):
        previous = self.book_loading
        self.book_loading = True
        records, failures = self.library_store.items()
        labels = {}
        for record in records:
            label = record['name']
            while label in labels:
                label += ' (copy)'
            labels[label] = record['id']
        if hasattr(self, 'library_rows'):
            self.library_records = records
            self.filter_library()
        self.book_labels = labels
        self.book_selector.items = list(labels)
        if self.book_record:
            self.book_selector.value = next((label for label, key in labels.items()
                                            if key == self.book_record['id']), None)
        if failures:
            self.book_status.text = f'{len(failures)} library record(s) could not be read; they were preserved.'
        self.book_loading = previous
