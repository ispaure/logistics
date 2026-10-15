"""One native editor and callback owner per open text/Markdown session."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .documents import document_name
from .action_menu import ActionMenu
from commonUtils.ui.native.editor_search import EditorSearch

FIELDS = ('selector', 'name', 'editor', 'status', 'recovery_notice', 'import_button',
          'save_button', 'export_button', 'document_view')


class TextEditorView:
    def __init__(self, app):
        self.app, self.document, self.session = app, None, None
        self.loading = True
        self.preview_pending = None
        self.split_preview = None
        self.selector = toga.Selection(on_change=self.selected, style=Pack(flex=1, height=44))
        self.name = toga.TextInput(placeholder='Document name', on_change=self.name_changed, style=Pack(flex=1, height=44))
        self.editor = toga.MultilineTextInput(on_change=self.text_changed,
            style=Pack(flex=1, font_size=int(app.preferences.values['font_size']), margin_top=4))
        self.status = toga.Label('', style=Pack(font_size=12, margin_top=4))
        self.recovery_notice = toga.Label('', style=Pack(font_size=12))
        self.import_button = toga.Button('Import…', on_press=app.import_document, style=Pack(flex=1, height=44))
        self.save_button = toga.Button('Save', on_press=app.save_document, style=Pack(flex=1, height=44))
        self.export_button = toga.Button('Export…', on_press=app.export_document, style=Pack(flex=1, height=44))
        box = self.document_view = toga.Box(style=Pack(direction=COLUMN, flex=1, margin=12))
        self.actions_button = toga.Button('•••', style=Pack(width=44, height=44))
        self.actions = ActionMenu(self.actions_button, self, [
            ('Open documents', app.show_documents_hub), ('New document', app.choose_document_type),
            ('Open beside another document', lambda: app.adaptive.show_pair_picker()),
            ('Import…', lambda: app.import_document(origin=self)), ('Open from Files…', app.show_editor_open),
            ('Save', app.save_document), ('Save a copy', app.save_copy),
            ('Save As…', app.show_document_save_as), ('Export…', lambda: app.export_document(origin=self)),
            ('Close document', lambda: app.request_close_session(self.session.id)),
            ('Preview beside editor (wide windows)', self.toggle_split)])
        # A visible left-hand editor still owns its toolbar commands.
        self.save_button.on_press = lambda widget, **kw: self.actions.invoke(app.save_document)
        box.add(toga.Box(children=[self.name, self.actions_button], style=Pack(direction=ROW, margin_bottom=8)))
        self.editor_area = toga.Box(children=[self.editor], style=Pack(direction=ROW, flex=1))
        box.add(self.editor_area)
        box.add(self.status)
        box.add(toga.Box(children=[self.save_button,
            toga.Button('Find', on_press=self.toggle_search, style=Pack(flex=1, height=44)),
            toga.Button('Preview', on_press=lambda widget, **kw: self.actions.invoke(app.show_preview), style=Pack(flex=1, height=44))],
            style=Pack(direction=ROW, margin_top=8)))
        self.search = EditorSearch(self.editor, self.document_view)
        app.register_transfer_status(box)

    def toggle_search(self, widget=None, **kwargs):
        self.search.toggle()

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
        if isinstance(getattr(self.app, '_main_window', None), toga.Window):
            self.apply_split(self.app.main_window.size.width)

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
            self.app.routes.update_title(self.document_view, self.document.name)
            self.app.adaptive.update_title(self.document_view, self.document.name)
        except ValueError:
            pass

    def text_changed(self, widget, **kwargs):
        if (self.loading or not self.app.active_host or self.document is None or self.session.id not in self.app.workspace.sessions
                or (self.app.loading and self.app.editor_view is self)):
            return
        self.document.text = widget.value
        self.search.changed()
        self.preserve()
        self.schedule_preview()

    def toggle_split(self):
        if self.session is None:
            return
        self.session.view['markdown_split'] = not self.session.view.get('markdown_split', False)
        self.apply_split(self.app.main_window.size.width)

    def apply_split(self, width):
        if self.session is None:
            return
        show = width >= 1100 and self.session.view.get('markdown_split', False)
        if show and self.split_preview is None:
            self.split_preview = toga.WebView(on_navigation_starting=lambda widget, url, **kw: False, style=Pack(flex=1))
        if show and self.split_preview not in self.editor_area.children:
            self.editor_area.add(self.split_preview)
            self.schedule_preview()
        elif not show and self.split_preview in self.editor_area.children:
            self.editor_area.remove(self.split_preview)

    def schedule_preview(self):
        if self.preview_pending is not None:
            self.preview_pending.cancel()
        if self.split_preview is None or self.split_preview not in self.editor_area.children:
            return
        token = self.app.workspace.token(self.session.id)
        def render():
            self.preview_pending = None
            if self.app.active_host and self.app.workspace.accepts(token):
                from .preview import markdown_preview
                from uuid import uuid4
                try:
                    self.split_preview.set_content('https://logistics.invalid/' + uuid4().hex + '/',
                        markdown_preview(self.document.text, int(self.app.preferences.values['font_size'])))
                except ValueError as error:
                    self.status.text = str(error)
        self.preview_pending = self.app.loop.call_later(.25, render)

    def dispose(self):
        self.actions.dispose()
        if self.preview_pending is not None:
            self.preview_pending.cancel()
            self.preview_pending = None
        if self.split_preview is not None:
            self.split_preview.set_content('https://logistics.invalid/closed/', '<p>Document closed.</p>')

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
