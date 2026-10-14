"""One native editor and callback owner per open text/Markdown session."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .documents import document_name
from .action_menu import ActionMenu

FIELDS = ('selector', 'name', 'editor', 'status', 'recovery_notice', 'import_button',
          'save_button', 'export_button', 'document_view')


class TextEditorView:
    def __init__(self, app):
        self.app, self.document, self.session = app, None, None
        self.loading = True
        self.selector = toga.Selection(on_change=self.selected, style=Pack(flex=1, height=44))
        self.name = toga.TextInput(on_change=self.name_changed, style=Pack(flex=1, height=44))
        self.editor = toga.MultilineTextInput(on_change=self.text_changed,
            style=Pack(flex=1, font_size=int(app.preferences.values['font_size'])))
        self.status = toga.Label('', style=Pack(font_size=12))
        self.recovery_notice = toga.Label('', style=Pack(font_size=12))
        self.import_button = toga.Button('Import…', on_press=app.import_document, style=Pack(flex=1, height=44))
        self.save_button = toga.Button('Save', on_press=app.save_document, style=Pack(flex=1, height=44))
        self.export_button = toga.Button('Export…', on_press=app.export_document, style=Pack(flex=1, height=44))
        box = self.document_view = toga.Box(style=Pack(direction=COLUMN, flex=1, margin=12))
        self.actions_button = toga.Button('Actions', style=Pack(height=44))
        self.actions = ActionMenu(self.actions_button, self, [
            ('Open documents', app.show_documents_hub), ('New document', app.new_document),
            ('Import…', lambda: app.import_document(origin=self)), ('Open from Files…', app.show_editor_open),
            ('Save', app.save_document), ('Save a copy', app.save_copy),
            ('Save As…', app.show_document_save_as), ('Export…', lambda: app.export_document(origin=self)),
            ('Close document', lambda: app.request_close_session(self.session.id))])
        box.add(toga.Box(children=[self.name, self.actions_button], style=Pack(direction=ROW, margin_bottom=8)))
        box.add(self.editor)
        box.add(self.status)
        box.add(toga.Box(children=[self.save_button,
            toga.Button('Preview', on_press=app.show_preview, style=Pack(flex=1, height=44))],
            style=Pack(direction=ROW, margin_top=8)))

    def load(self, document, session):
        self.document, self.session = document, session
        self.loading = True
        self.name.value, self.editor.value = document.name, document.text
        self.status.text = ('Stored file changed. Save a copy to keep recovered edits.' if document.conflict
                            else 'Recovered unsaved edits.' if document.modified else 'Saved')
        self.loading = False

    def bind(self):
        self.app.editor_view = self
        self.app.current = self.document
        for field in FIELDS:
            setattr(self.app, field, getattr(self, field))

    def selected(self, widget, **kwargs):
        if not self.loading and self.app.editor_view is self:
            self.app.select_document(widget, **kwargs)

    def name_changed(self, widget, **kwargs):
        if (self.loading or not self.app.active_host or self.document is None or self.session.id not in self.app.workspace.sessions
                or (self.app.loading and self.app.editor_view is self)):
            return
        try:
            self.document.name = document_name(widget.value)
            self.session.title = self.document.name
            self.session.kind = 'markdown' if self.document.name.lower().endswith(('.md', '.markdown')) else 'text'
            self.preserve()
        except ValueError:
            pass

    def text_changed(self, widget, **kwargs):
        if (self.loading or not self.app.active_host or self.document is None or self.session.id not in self.app.workspace.sessions
                or (self.app.loading and self.app.editor_view is self)):
            return
        self.document.text = widget.value
        self.preserve()

    def preserve(self):
        if self.session.id not in self.app.workspace.sessions:
            return
        self.session.dirty = self.document.modified
        if getattr(self.document, 'private', False):
            self.status.text = 'Session-only draft. Save it before closing.'
            return
        try:
            self.app.store.checkpoint(self.document)
            self.status.text = 'Draft preserved' if self.document.modified else 'Saved'
        except (OSError, ValueError) as error:
            self.status.text = 'Could not preserve edits: ' + str(error)

    def capture(self):
        if self.session is None:
            return
        backend = type(self.editor._impl).__module__
        native = getattr(self.editor._impl, 'native', None)
        if backend.startswith('toga_android.'):
            start, end = max(0, int(native.getSelectionStart())), max(0, int(native.getSelectionEnd()))
            self.session.view.update(cursor=start, selection_length=max(0, end - start),
                scroll_x=max(0, int(native.getScrollX())), scroll_y=max(0, int(native.getScrollY())))
        elif backend.startswith('toga_iOS.'):
            selection, offset = native.selectedRange, native.contentOffset
            size = len(self.document.text.encode('utf-16-le')) // 2
            self.session.view.update(cursor=min(size, int(selection.location)), selection_length=min(size, int(selection.length)),
                scroll_x=max(0, int(offset.x)), scroll_y=max(0, int(offset.y)))

    def restore(self):
        if self.session is None:
            return
        state = self.session.view
        size = len(self.document.text.encode('utf-16-le')) // 2
        start = min(size, state.get('cursor', 0))
        end = min(size, start + state.get('selection_length', 0))
        backend = type(self.editor._impl).__module__
        native = getattr(self.editor._impl, 'native', None)
        if backend.startswith('toga_android.'):
            native.setSelection(start, end)
            native.scrollTo(state.get('scroll_x', 0), state.get('scroll_y', 0))
        elif backend.startswith('toga_iOS.'):
            from rubicon.objc import NSRange, CGPoint
            native.selectedRange = NSRange(start, end - start)
            native.setContentOffset(CGPoint(state.get('scroll_x', 0), state.get('scroll_y', 0)), animated=False)
