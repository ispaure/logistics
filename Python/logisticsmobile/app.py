"""Small native mobile text/Markdown prototype with app-private recovery."""
import asyncio
from pathlib import Path
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .documents import DocumentStore, document_name


class LogisticsMobile(toga.App):
    storage_root = None  # Host tests may supply a private fixture directory.

    def startup(self):
        self.store = DocumentStore(Path(self.storage_root or self.paths.data) / 'Documents')
        self.current = None
        self.loading = True
        self.labels = {}
        self.selector = toga.Selection(on_change=self.select_document, style=Pack(flex=1, height=44))
        self.name = toga.TextInput(on_change=self.name_changed, style=Pack(flex=1, height=44))
        self.editor = toga.MultilineTextInput(on_change=self.text_changed, style=Pack(flex=1))
        self.status = toga.Label('', style=Pack(font_size=12))
        self.recovery_notice = toga.Label('', style=Pack(font_size=12))
        self.import_button = toga.Button('Import…', on_press=self.import_document, style=Pack(flex=1, height=44))
        self.save_button = toga.Button('Save', on_press=self.save_document, style=Pack(flex=1, height=44))
        box = toga.Box(style=Pack(direction=COLUMN, margin=12))
        box.add(toga.Box(children=[self.selector], style=Pack(direction=ROW, margin_bottom=8)))
        box.add(self.recovery_notice)
        box.add(toga.Box(children=[toga.Button('New', on_press=self.new_document, style=Pack(flex=1, height=44)),
                                   self.import_button], style=Pack(direction=ROW, margin_bottom=8)))
        box.add(toga.Box(children=[self.name], style=Pack(direction=ROW, margin_bottom=8)))
        box.add(self.editor)
        box.add(self.status)
        box.add(toga.Box(children=[self.save_button,
            toga.Button('Save a copy', on_press=self.save_copy, style=Pack(flex=1, height=44))],
            style=Pack(direction=ROW, margin_top=8)))
        self.main_window = toga.MainWindow(title='Logistics', content=box,
                                           on_lose_focus=self.checkpoint)
        self.on_exit = self.exit_app
        self.refresh_documents()
        self.loading = False
        if self.labels:
            self.open_document(next(iter(self.labels.values())))
        else:
            self.new_document()
        self.main_window.show()

    def refresh_documents(self):
        previous = self.loading
        self.loading = True
        documents, failures = self.store.documents()
        counts, self.labels = {}, {}
        for doc in documents:
            counts[doc.name] = counts.get(doc.name, 0) + 1
            label = doc.name + (f' ({counts[doc.name]})' if counts[doc.name] > 1 else '')
            while label in self.labels:
                label += ' (copy)'
            self.labels[label] = doc.id
        self.selector.items = list(self.labels)
        if self.current:
            self.selector.value = next((label for label, key in self.labels.items()
                                        if key == self.current.id), None)
        self.loading = previous
        self.recovery_notice.text = (f'{len(failures)} recovery record(s) could not be opened; they were preserved.'
                                     if failures else '')

    def open_document(self, key):
        self.loading = True
        try:
            self.current = self.store.open(key)
            self.name.value = self.current.name
            self.editor.value = self.current.text
            self.status.text = ('Stored file changed. Save a copy to keep recovered edits.' if self.current.conflict
                                else 'Recovered unsaved edits.' if self.current.modified else 'Saved')
            self.selector.value = next((label for label, identity in self.labels.items() if identity == key), None)
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.status.text = str(error)
        finally:
            self.loading = False

    def select_document(self, widget, **kwargs):
        if not self.loading and widget.value in self.labels:
            if self.checkpoint():
                self.open_document(self.labels[widget.value])

    def new_document(self, widget=None, **kwargs):
        if not self.checkpoint():
            return
        try:
            self.current = self.store.create()
            self.refresh_documents()
            self.open_document(self.current.id)
        except (OSError, ValueError) as error:
            self.status.text = str(error)

    def name_changed(self, widget, **kwargs):
        if self.loading or self.current is None:
            return
        try:
            self.current.name = document_name(widget.value)
            self.checkpoint()
        except ValueError:
            pass  # Allow an empty field while the user replaces its name.

    def text_changed(self, widget, **kwargs):
        if self.loading or self.current is None:
            return
        self.current.text = widget.value
        if self.checkpoint():
            self.status.text = 'Draft preserved' if self.current.modified else 'Saved'

    def checkpoint(self, *args, **kwargs):
        if self.current is None or self.loading:
            return True
        try:
            self.store.checkpoint(self.current)
            return True
        except (OSError, ValueError) as error:
            self.status.text = 'Could not preserve edits: ' + str(error)
            return False

    def save_document(self, widget=None, **kwargs):
        try:
            self.current.name = document_name(self.name.value)
            self.store.save(self.current)
            self.refresh_documents()
            self.status.text = 'Saved'
        except (OSError, ValueError) as error:
            self.status.text = str(error)

    def save_copy(self, widget=None, **kwargs):
        try:
            copy = self.store.save_copy(self.current, document_name(self.name.value))
            self.current = copy
            self.refresh_documents()
            self.open_document(copy.id)
        except (OSError, ValueError) as error:
            self.status.text = str(error)

    async def import_document(self, widget=None, **kwargs):
        from .pickers import pick_document
        if not self.checkpoint():
            return
        self.import_button.enabled = False
        try:
            selected = await pick_document(self)
            if selected:
                self.current = await asyncio.to_thread(self.store.import_document, *selected)
                self.refresh_documents()
                self.open_document(self.current.id)
        except Exception as error:
            # Native bridge errors are not necessarily OSError subclasses.
            self.status.text = 'Import failed: ' + str(error)[:500]
        finally:
            self.import_button.enabled = True

    def exit_app(self, app, **kwargs):
        return self.checkpoint()


def main():
    return LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
