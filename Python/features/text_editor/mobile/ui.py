"""One native editor and callback owner per open text/Markdown session."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from features.text_editor.names import document_name
from commonUtils.ui.native.editor_search import EditorSearch
from commonUtils.ui.native.code_input import CodeInput
from commonUtils.formats.code_syntax import LANGUAGES
from commonUtils.ui.native.adaptive import allocated_width

FIELDS = ('selector', 'name', 'editor', 'status', 'recovery_notice', 'import_button',
          'save_button', 'export_button', 'document_view')


def document_status(document):
    if getattr(document, 'private', False):
        return 'Unsaved changes · session only. Save before closing.' if document.modified else 'Session only'
    if document.conflict:
        return 'File changed outside the editor. Save a copy to keep your edits.'
    return 'Unsaved changes · recovery copy kept' if document.modified else 'Saved on this device'


class TextEditorView:
    def __init__(self, app):
        self.app, self.document, self.session = app, None, None
        icon_button, apply_icon = app.presentation.icon_button, app.presentation.apply_icon
        action_button, ActionMenu = app.presentation.action_button, app.presentation.ActionMenu
        self.loading = True
        self.preview_pending = None
        self.split_preview = None
        self.selector = toga.Selection(on_change=self.selected, style=Pack(flex=1, height=48))
        self.name = toga.TextInput(placeholder='Document name', on_change=self.name_changed, style=Pack(flex=1, height=48))
        self.editor = CodeInput(loop=app.loop, on_change=self.text_changed,
            style=Pack(flex=1, font_size=int(app.preferences.values['font_size']), margin_top=4))
        if self.editor.backend_name.startswith('toga_iOS.'):
            # The source editor constructs its own native text view, bypassing
            # the ordinary Toga input creation hook used by host appearance.
            from rubicon.objc import SEL
            native = self.editor._impl.native
            for edge in ('topEdgeEffect', 'bottomEdgeEffect'):
                if native.respondsToSelector(SEL(edge)):
                    getattr(native, edge).hidden = True
        self.language_choice = toga.Selection(items=['Automatic', *[name for name, code in LANGUAGES]],
            on_change=self.language_changed, style=Pack(flex=1, height=48))
        self.line_count = toga.Label('1 line', style=Pack(margin=8))
        self.live_button = toga.Button('Live preview', on_press=lambda widget, **kw: self.toggle_split(), style=Pack(height=48))
        self.status = toga.Label('', style=Pack(font_size=12, margin_top=4))
        self.recovery_notice = toga.Label('', style=Pack(font_size=12))
        self.import_button = toga.Button('Import…', on_press=app.import_document, style=Pack(flex=1, height=48))
        self.save_button = action_button(toga.Button('Save', on_press=app.save_document, style=Pack(flex=1, height=48)))
        self.export_button = toga.Button('Export…', on_press=app.export_document, style=Pack(flex=1, height=48))
        box = self.document_view = toga.Box(style=Pack(direction=COLUMN, flex=1, margin=12))
        self.actions_button = icon_button('more', 'Document actions')
        self.conflict_actions = toga.Box(style=Pack(direction=COLUMN))
        self.conflict_copy = toga.Button('Save a copy…',
            on_press=lambda widget, **kw: self.actions.invoke(app.save_copy), style=Pack(height=48))
        self.actions = ActionMenu(self.actions_button, self, [
            ('Open documents', app.show_documents_hub), ('New document', app.choose_document_type),
            ('Open beside another document', lambda: app.adaptive.show_pair_picker()),
            ('Import…', lambda: app.import_document(origin=self)), ('Open from Files…', app.show_editor_open),
            ('Save', app.save_document), ('Save a copy', app.save_copy),
            ('Save As…', app.show_document_save_as), ('Export…', lambda: app.export_document(origin=self)),
            ('Close document', lambda: app.request_close_session(self.session.id)),
            ('Show/hide live preview', self.toggle_split)])
        # A visible left-hand editor still owns its toolbar commands.
        self.save_button.on_press = lambda widget, **kw: self.actions.invoke(app.save_document)
        box.add(toga.Box(children=[self.name, self.actions_button], style=Pack(direction=ROW, margin_bottom=8)))
        box.add(toga.Box(children=[self.language_choice, self.line_count, self.live_button], style=Pack(direction=ROW)))
        self.editor_area = toga.Box(children=[self.editor], style=Pack(direction=ROW, flex=1))
        box.add(self.editor_area)
        box.add(self.status)
        box.add(self.conflict_actions)
        box.add(toga.Box(children=[self.save_button,
            icon_button('find', 'Find and replace', on_press=self.toggle_search),
            toga.Button('Preview', on_press=lambda widget, **kw: self.actions.invoke(app.show_preview), style=Pack(flex=1, height=48))],
            style=Pack(direction=ROW, margin_top=8)))
        self.search = EditorSearch(self.editor, self.document_view)
        previous, next_match = self.search.box.children[1].children
        previous.style.flex = next_match.style.flex = 0
        apply_icon(previous, 'back', 'Previous match')
        apply_icon(next_match, 'forward', 'Next match')
        app.register_transfer_status(box)

    def toggle_search(self, widget=None, **kwargs):
        self.search.toggle()

    def load(self, document, session):
        self.document, self.session = document, session
        self.loading = True
        self.name.value, self.editor.value = document.name, document.text
        self.editor.set_filename(document.name)
        session.view.setdefault('markdown_split', session.kind == 'markdown')
        self.update_source_info()
        self.refresh_status()
        self.loading = False

    def refresh_status(self):
        self.status.text = document_status(self.document)
        conflict = not getattr(self.document, 'private', False) and self.document.conflict
        if conflict and self.conflict_copy not in self.conflict_actions.children:
            self.conflict_actions.add(self.conflict_copy)
        elif not conflict and self.conflict_copy in self.conflict_actions.children:
            self.conflict_actions.remove(self.conflict_copy)

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
            self.editor.set_filename(self.document.name)
            self.update_source_info()
            self.apply_split(self.app.main_window.size.width)
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
        self.update_source_info()
        self.preserve()
        self.schedule_preview()

    def update_source_info(self):
        count = len(self.editor.line_starts)
        self.line_count.text = f'{count} line' + ('s' if count != 1 else '')
        if self.session is not None:
            self.live_button.enabled = self.session.kind == 'markdown'

    def language_changed(self, widget, **kwargs):
        if not hasattr(self, 'editor'):
            return
        self.editor.set_language(dict(LANGUAGES).get(widget.value))

    def toggle_split(self):
        if self.session is None:
            return
        self.session.view['markdown_split'] = not self.session.view.get('markdown_split', False)
        self.apply_split(self.app.main_window.size.width)
        self.app.save_workspace()

    def apply_split(self, width):
        if self.session is None:
            return
        show = self.session.kind == 'markdown' and self.session.view.get('markdown_split', True)
        usable_width = allocated_width(self.editor_area, width)
        self.editor_area.style.direction = ROW if usable_width >= 720 else COLUMN
        self.live_button.text = 'Hide preview' if show else 'Live preview'
        if show and self.split_preview is None:
            self.split_preview = toga.WebView(on_navigation_starting=lambda widget, url, **kw: False, style=Pack(flex=1))
        if show and self.split_preview not in self.editor_area.children:
            self.editor_area.add(self.split_preview)
            self.schedule_preview()
        elif not show and self.split_preview in self.editor_area.children:
            self.editor_area.remove(self.split_preview)
            if self.preview_pending is not None:
                self.preview_pending.cancel()
                self.preview_pending = None

    def schedule_preview(self):
        if self.preview_pending is not None:
            self.preview_pending.cancel()
        if self.split_preview is None or self.split_preview not in self.editor_area.children:
            return
        token = self.app.workspace.token(self.session.id)
        def render():
            self.preview_pending = None
            if self.app.active_host and self.app.workspace.accepts(token):
                markdown_preview = self.app.presentation.markdown_preview
                from uuid import uuid4
                try:
                    self.split_preview.set_content('https://logistics.invalid/' + uuid4().hex + '/',
                        markdown_preview(self.document.text, int(self.app.preferences.values['font_size'])))
                except ValueError as error:
                    self.status.text = str(error)
        self.preview_pending = self.app.loop.call_later(.25, render)

    def dispose(self):
        self.editor.dispose()
        self.actions.dispose()
        if self.preview_pending is not None:
            self.preview_pending.cancel()
            self.preview_pending = None
        if self.split_preview is not None:
            if type(self.split_preview._impl).__module__.startswith('toga_iOS.'):
                # WebKit can ask for a navigation decision after the closed
                # Toga interface has been collected. Retire its weak delegates
                # before replacing the document or releasing the widget.
                native = self.split_preview._impl.native
                native.stopLoading()
                native.navigationDelegate = None
                native.UIDelegate = None
            self.split_preview.set_content('https://logistics.invalid/closed/', '<p>Document closed.</p>')

    def preserve(self):
        if self.session.id not in self.app.workspace.sessions:
            return
        self.session.dirty = self.document.modified
        if getattr(self.document, 'private', False):
            self.refresh_status()
            return
        try:
            self.app.store.checkpoint(self.document)
            self.refresh_status()
        except (OSError, ValueError) as error:
            self.status.text = 'Could not preserve edits: ' + str(error)

    def capture(self):
        if self.session is None:
            return
        backend = self.editor.backend_name
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
        backend = self.editor.backend_name
        native = getattr(self.editor._impl, 'native', None)
        if backend.startswith('toga_android.'):
            native.setSelection(start, end)
            native.scrollTo(state.get('scroll_x', 0), state.get('scroll_y', 0))
        elif backend.startswith('toga_iOS.'):
            from rubicon.objc import NSRange, CGPoint
            native.selectedRange = NSRange(start, end - start)
            native.setContentOffset(CGPoint(state.get('scroll_x', 0), state.get('scroll_y', 0)), animated=False)
