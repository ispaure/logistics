"""Small native mobile text/Markdown prototype with app-private recovery."""
import asyncio
from pathlib import Path
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .documents import DocumentStore, document_name
from .preferences import Preferences
from .preview import markdown_preview
from .library_ui import LibraryUI
from .chat_ui import ChatUI


class LogisticsMobile(LibraryUI, ChatUI, toga.App):
    storage_root = None  # Host tests may supply a private fixture directory.

    def startup(self):
        root = Path(self.storage_root or self.paths.data)
        self.private_root = root
        self.preferences = Preferences(root)
        self.store = DocumentStore(root / 'Documents')
        self.current = None
        self.loading = True
        self.labels = {}
        self.selector = toga.Selection(on_change=self.select_document, style=Pack(flex=1, height=44))
        self.name = toga.TextInput(on_change=self.name_changed, style=Pack(flex=1, height=44))
        self.editor = toga.MultilineTextInput(on_change=self.text_changed,
            style=Pack(flex=1, font_size=int(self.preferences.values['font_size'])))
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
        self.export_button = toga.Button('Export…', on_press=self.export_document, style=Pack(flex=1, height=44))
        box.add(toga.Box(children=[self.export_button,
            toga.Button('Preview', on_press=self.show_preview, style=Pack(flex=1, height=44))],
            style=Pack(direction=ROW, margin_top=8)))
        self.document_view = box
        self.body = toga.Box(style=Pack(direction=COLUMN, flex=1))
        self.navigation = toga.Box(children=[
            toga.Button('Home', on_press=self.show_home, style=Pack(flex=1, height=44)),
            toga.Button('Documents', on_press=self.show_documents, style=Pack(flex=1, height=44)),
            toga.Button('Settings', on_press=self.show_settings, style=Pack(flex=1, height=44))],
            style=Pack(direction=ROW))
        shell = toga.Box(children=[self.navigation, self.body], style=Pack(direction=COLUMN))
        self.main_window = toga.MainWindow(title='Logistics', content=shell,
                                           on_lose_focus=self.checkpoint)
        self.on_exit = self.exit_app
        self.refresh_documents()
        self.loading = False
        if self.labels:
            key = self.preferences.values['last_document']
            if self.preferences.values['restore_last_document'] != 'true' or key not in self.labels.values():
                key = next(iter(self.labels.values()))
            self.open_document(key)
        else:
            self.new_document()
        self.show_home()
        self.main_window.show()

    def show_view(self, view):
        if not self.checkpoint():
            return False
        for child in list(self.body.children):
            self.body.remove(child)
        self.body.add(view)
        return True

    def show_home(self, widget=None, **kwargs):
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(toga.Label('Logistics', style=Pack(font_size=24, margin_bottom=12)))
        box.add(toga.Label('Your documents, on this device.', style=Pack(margin_bottom=12)))
        box.add(toga.Button('Text & Markdown', on_press=self.show_documents, style=Pack(height=52)))
        box.add(toga.Button('Books & Comics', on_press=self.show_library, style=Pack(height=52, margin_top=8)))
        box.add(toga.Button('LM Chat', on_press=self.show_chat, style=Pack(height=52, margin_top=8)))
        box.add(toga.Label(f'{len(self.labels)} private document(s)', style=Pack(margin_top=8)))
        box.add(toga.Label('Remote files are coming\nin the next phase.',
                           style=Pack(margin_top=16)))
        if self.preferences.error:
            box.add(toga.Label(self.preferences.error, style=Pack(margin_top=12)))
        self.show_view(box)

    def show_documents(self, widget=None, **kwargs):
        self.show_view(self.document_view)

    def show_settings(self, widget=None, **kwargs):
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(toga.Label('Preferences', style=Pack(font_size=22, margin_bottom=12)))
        self.font_choice = toga.Selection(items=['12', '14', '16', '18', '20', '24', '28', '32'],
            value=self.preferences.values['font_size'], style=Pack(height=44))
        self.restore_choice = toga.Switch('Restore last document',
            value=self.preferences.values['restore_last_document'] == 'true', style=Pack(height=44))
        self.settings_status = toga.Label(self.preferences.error, style=Pack(margin_top=12))
        box.add(toga.Label('Editor and preview font size'))
        box.add(self.font_choice)
        box.add(self.restore_choice)
        box.add(toga.Button('Save preferences', on_press=self.save_preferences, style=Pack(height=44)))
        box.add(toga.Button('Reload preferences', on_press=self.reload_preferences, style=Pack(height=44)))
        box.add(self.settings_status)
        self.show_view(box)

    def save_preferences(self, widget=None, **kwargs):
        try:
            self.preferences.save(font_size=self.font_choice.value,
                restore_last_document='true' if self.restore_choice.value else 'false')
            self.editor.style.font_size = int(self.preferences.values['font_size'])
            self.settings_status.text = 'Preferences saved on this device.'
        except (OSError, ValueError) as error:
            self.settings_status.text = str(error)

    def reload_preferences(self, widget=None, **kwargs):
        self.preferences.reload()
        self.editor.style.font_size = int(self.preferences.values['font_size'])
        self.show_settings()

    def show_preview(self, widget=None, **kwargs):
        if self.current is None or not self.checkpoint():
            return
        try:
            content = markdown_preview(self.current.text, int(self.preferences.values['font_size']))
        except ValueError as error:
            self.status.text = str(error)
            return
        self.preview = toga.WebView(on_navigation_starting=lambda widget, url, **kw: False,
                                   style=Pack(flex=1))
        # A fresh WebView may still be navigating to its initial about:blank.
        # Give the HTML load a distinct local-document origin so that blank
        # navigation cannot consume Toga's one approved content navigation.
        self.preview.set_content('https://logistics.invalid/', content)
        self.show_view(toga.Box(children=[
            toga.Button('Back to editor', on_press=self.show_documents, style=Pack(height=44)),
            self.preview], style=Pack(direction=COLUMN, flex=1)))

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
            try:
                self.preferences.save(last_document=key)
            except (OSError, ValueError) as error:
                self.status.text += ' · ' + str(error)
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
        if self.current is None:
            return
        try:
            self.current.name = document_name(self.name.value)
            self.store.save(self.current)
            self.refresh_documents()
            self.status.text = 'Saved'
        except (OSError, ValueError) as error:
            self.status.text = str(error)

    def save_copy(self, widget=None, **kwargs):
        if self.current is None:
            return
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

    async def export_document(self, widget=None, **kwargs):
        from .pickers import export_document
        if self.current is None or not self.checkpoint():
            return
        self.export_button.enabled = False
        try:
            done = await export_document(self, document_name(self.name.value),
                                        self.current.snapshot.encode(self.current.text))
            self.status.text = 'Document copy exported.' if done else 'Export cancelled.'
        except Exception as error:
            self.status.text = 'Export failed: ' + str(error)[:500]
        finally:
            self.export_button.enabled = True

    def exit_app(self, app, **kwargs):
        if getattr(self, 'chat_client', None):
            self.chat_client.cancel()
        if hasattr(self, 'chat_current') and not self.checkpoint_chat():
            return False
        return self.checkpoint()


def main():
    return LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
