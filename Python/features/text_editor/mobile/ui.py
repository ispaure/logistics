"""One native editor and callback owner per open text/Markdown session."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from features.text_editor.names import document_name
from commonUtils.ui.native.editor_search import EditorSearch
from commonUtils.ui.native.code_input import CodeInput
from commonUtils.formats.code_syntax import LANGUAGES
from .markdown_editor import FormattedMarkdownInput
from logisticsmobile.font_scaling import bind, font_size

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
        ActionMenu = app.presentation.ActionMenu
        self.loading = True
        self.formatted = None
        self.preview = self.preview_box = None
        self.selector = toga.Selection(on_change=self.selected, style=Pack(flex=1, height=48))
        self.name = toga.TextInput(placeholder='Document name', on_change=self.name_changed, style=Pack(flex=1, height=48))
        self.editor = CodeInput(loop=app.loop, on_change=self.text_changed,
            highlighting=app.preferences.values.get('android_eink') != 'true',
            style=Pack(flex=1, font_size=font_size(app, 'text'), margin_top=4))
        bind(app, self.editor, lambda: self.session.kind if self.session else 'text')
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
        self.edit_mode = toga.Selection(items=['Formatted', 'Source'], on_change=self.mode_changed,
            style=Pack(flex=1, height=48))
        self.status = toga.Label('', style=Pack(font_size=12, margin_top=4))
        self.recovery_notice = toga.Label('', style=Pack(font_size=12))
        self.import_button = toga.Button('Import…', on_press=app.import_document, style=Pack(flex=1, height=48))
        self.save_button = icon_button('save', 'Save document', on_press=app.save_document)
        self.export_button = toga.Button('Export…', on_press=app.export_document, style=Pack(flex=1, height=48))
        box = self.document_view = toga.Box(style=Pack(direction=COLUMN, flex=1, margin=12))
        self.actions_button = icon_button('more', 'Document actions')
        self.conflict_actions = toga.Box(style=Pack(direction=COLUMN))
        self.conflict_copy = toga.Button('Save a copy…',
            on_press=lambda widget, **kw: self.actions.invoke(app.save_copy), style=Pack(height=48))
        self.action_items = [
            ('Open documents', app.show_documents_hub), ('New document', app.choose_document_type),
            ('Open beside another document', lambda: app.adaptive.show_pair_picker()),
            ('Import…', lambda: app.import_document(origin=self)), ('Open from Files…', app.show_editor_open),
            ('Save', app.save_document), ('Save a copy', app.save_copy),
            ('Save As…', app.show_document_save_as), ('Export…', lambda: app.export_document(origin=self)),
            ('Close document', lambda: app.request_close_session(self.session.id)),
            ('Delete document…', lambda: app.request_delete_document(self.session.id))]
        self.save_visible = False
        self.actions = ActionMenu(self.actions_button, self,
            [item for item in self.action_items if item[0] != 'Save'])
        # A visible left-hand editor still owns its toolbar commands.
        self.save_button.on_press = lambda widget, **kw: self.actions.invoke(app.save_document)
        self.preview_button = icon_button('view', 'View document',
            on_press=lambda widget, **kw: self.actions.invoke(app.show_preview))
        self.toolbar = toga.Box(children=[self.name,
            icon_button('find', 'Find and replace', on_press=self.toggle_search),
            self.preview_button, self.actions_button], style=Pack(direction=ROW))
        box.add(self.toolbar)
        box._workspace_toolbar = self.toolbar
        self.source_tools = toga.Box(children=[self.language_choice, self.line_count], style=Pack(direction=ROW))
        box.add(self.source_tools)
        self.editor_area = toga.Box(children=[self.editor], style=Pack(direction=ROW, flex=1))
        box.add(self.editor_area)
        box.add(self.status)
        box.add(self.conflict_actions)
        self.search = EditorSearch(self.editor, self.document_view)
        previous, next_match = self.search.box.children[1].children
        previous.style.flex = next_match.style.flex = 0
        apply_icon(previous, 'back', 'Previous match')
        apply_icon(next_match, 'forward', 'Next match')
        app.register_transfer_status(box)

    def toggle_search(self, widget=None, **kwargs):
        if self.session is not None and self.session.kind == 'markdown':
            self.edit_mode.value = 'Source'
        self.search.toggle()

    def load(self, document, session):
        self.document, self.session = document, session
        self.loading = True
        self.name.value, self.editor.value = document.name, document.text
        self.editor.set_filename(document.name)
        session.view.setdefault('markdown_editor', 'formatted')
        session.view.pop('markdown_split', None)
        self.edit_mode.value = 'Source' if session.view['markdown_editor'] == 'source' else 'Formatted'
        self.update_source_info()
        self.apply_split(0)
        self.refresh_status()
        self.loading = False

    def refresh_status(self):
        status = document_status(self.document)
        if self.status.text != status:
            self.status.text = status
        dirty = bool(self.document.modified)
        self.save_button.enabled = dirty
        from logisticsmobile.document_sources import folder_action
        folder_actions = folder_action(self.app, self.session)
        menu_state = dirty, bool(folder_actions)
        if menu_state != getattr(self, '_action_state', None):
            self._action_state = menu_state
            self.save_visible = dirty
            self.actions.dispose()
            actions = [item for item in self.action_items if dirty or item[0] != 'Save'] + folder_actions
            self.actions = self.app.presentation.ActionMenu(self.actions_button, self, actions)
            if dirty and self.save_button not in self.toolbar.children:
                self.toolbar.insert(1, self.save_button)
            elif not dirty and self.save_button in self.toolbar.children:
                self.toolbar.remove(self.save_button)
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
        caption = f'{count} line' + ('s' if count != 1 else '')
        if self.line_count.text != caption:
            self.line_count.text = caption
        if self.session is not None:
            markdown = self.session.kind == 'markdown'
            if markdown and self.edit_mode not in self.source_tools.children:
                self.source_tools.insert(0, self.edit_mode)
            elif not markdown and self.edit_mode in self.source_tools.children:
                self.source_tools.remove(self.edit_mode)
            source = not markdown or self.session.view.get('markdown_editor') == 'source'
            for control in (self.language_choice, self.line_count):
                if source and control not in self.source_tools.children:
                    self.source_tools.add(control)
                elif not source and control in self.source_tools.children:
                    self.source_tools.remove(control)

    def language_changed(self, widget, **kwargs):
        if not hasattr(self, 'editor'):
            return
        self.editor.set_language(dict(LANGUAGES).get(widget.value))

    def mode_changed(self, widget=None, **kwargs):
        if self.loading or self.session is None:
            return
        self.session.view['markdown_editor'] = 'source' if self.edit_mode.value == 'Source' else 'formatted'
        self.apply_split(0)
        self.update_source_info()
        self.app.save_workspace()

    def apply_split(self, width):
        """Keep one editing surface at every width, including restored old splits."""
        if self.session is None:
            return
        self.editor.style.font_size = font_size(self.app, self.session.kind)
        rich = self.session.kind == 'markdown' and self.session.view.get('markdown_editor', 'formatted') == 'formatted'
        surface = self.editor
        if rich:
            if self.formatted is None:
                self.formatted = FormattedMarkdownInput(self.formatted_changed,
                    font_size=font_size(self.app, 'markdown'),
                    stylesheet=self.app.presentation.css_variables())
                bind(self.app, self.formatted.view, 'markdown', web=True, formatted=self.formatted)
            try:
                self.formatted.load(self.document.text)
                surface = self.formatted.view
            except ValueError as error:
                self.status.text = str(error)
                self.session.view['markdown_editor'] = 'source'
                self.edit_mode.value = 'Source'
        if self.editor_area.children != [surface]:
            self.editor_area.clear()
            self.editor_area.add(surface)

    def formatted_changed(self, text):
        if (self.loading or not self.app.active_host or self.session is None
                or self.session.id not in self.app.workspace.sessions
                or self.formatted is None or self.formatted.view not in self.editor_area.children):
            return
        # Keep the native source input as the canonical buffer used by search,
        # save, recovery and export. Do not reload the WebView during typing.
        self.editor.value = text

    def schedule_preview(self):
        # Source callbacks may also come from find/replace or external reloads.
        if self.formatted is not None and self.formatted.view in self.editor_area.children:
            try:
                self.formatted.load(self.document.text)
            except ValueError as error:
                self.status.text = str(error)

    def dispose(self):
        speech = getattr(self, "markdown_speech", None)
        if speech is not None:
            speech.close()
        self.editor.dispose()
        self.actions.dispose()
        if hasattr(self, 'preview_actions'):
            self.preview_actions.dispose()
        if self.formatted is not None:
            self.formatted.dispose()
        if self.preview is not None:
            from .markdown_editor import retire_webview
            retire_webview(self.preview)

    def preserve(self):
        if self.session.id not in self.app.workspace.sessions:
            return
        self.session.dirty = self.document.modified
        if getattr(self.document, 'private', False):
            self.refresh_status()
            return
        try:
            def failed(error):
                if self.session.id in self.app.workspace.sessions and self.app.active_host:
                    self.status.text = 'Could not preserve edits: ' + str(error)
            self.app.store.queue_checkpoint(self.document, self.app.loop, failed=failed)
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
