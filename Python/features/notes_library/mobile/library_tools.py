"""Contents, source find/replace and YAML tools for the mobile Notes Library."""
import json
from datetime import date, datetime
from textwrap import fill, shorten
import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from commonUtils.formats.markdown import (
    split_frontmatter, parse_properties, parse_property_value, replace_property, replace_frontmatter,
    RawYAML,
)
from services.documents.authoring.document_dialogs import DocumentTypeDialog


def select_source(source, start, end):
    """Native text controls index UTF-16; Python match positions index characters."""
    source.focus()
    before = len(source.value[:start].encode('utf-16-le')) // 2
    after = len(source.value[:end].encode('utf-16-le')) // 2
    native = getattr(source._impl, 'native', None)
    backend = type(source._impl).__module__
    if backend.startswith('toga_iOS.'):
        from rubicon.objc import NSRange
        native.selectedRange = NSRange(before, after - before)
        native.scrollRangeToVisible(native.selectedRange)
    elif backend.startswith('toga_android.'):
        native.setSelection(before, after)
    source._library_selection = (start, end)


def clear_tool(widget):
    for child in getattr(widget, 'children', ()):
        clear_tool(child)
    if isinstance(widget, (toga.TextInput, toga.MultilineTextInput)):
        widget.value = ''
    elif isinstance(widget, toga.Label):
        widget.text = ''
    elif isinstance(widget, toga.Button):
        widget.on_press = None
        widget.text = ''
        widget.accessible_name = ''


async def show_contents(library, widget=None, **kwargs):
    if not library.valid() or library.path is None:
        return
    editor, epoch = library.embedded, library.epoch
    try:
        if editor is not None and hasattr(editor, 'show_contents'):
            return await editor.show_contents()
        raw = await library.web.evaluate_javascript(
            'JSON.stringify(Array.from(document.querySelectorAll("h1,h2,h3,h4,h5,h6"))'
            '.map(h=>({title:h.textContent,id:h.id,level:Number(h.tagName[1])})))')
        headings = json.loads(raw or '[]')
        if not library.valid() or library.epoch != epoch:
            return
        choices = [('  ' * (h['level'] - 1) + h['title'], str(index)) for index, h in enumerate(headings)]
        if not choices:
            library.notice.text = 'This document has no headings.'
            return
        dialog = DocumentTypeDialog(choices=choices)
        dialog.title, dialog.message = 'Contents', 'Jump to a heading.'
        selected = await library.view.window.dialog(dialog)
        if library.valid() and library.epoch == epoch and selected in {value for _, value in choices}:
            library.scroll_fragment(headings[int(selected)]['id'])
    except (TypeError, ValueError) as error:
        if library.valid() and library.epoch == epoch:
            library.notice.text = str(error)


class LibraryTools:
    def retire_tools(self):
        finder = getattr(self, 'finder', None)
        if finder is not None:
            finder.dispose()
            finder.query.value = ''
            finder.replacement.value = ''
        for content in getattr(self, 'tool_views', ()):
            clear_tool(content)
        self.tool_views = []
        self.find_match = None

    def tools_current(self):
        return not self.closed and self.library.valid() and self.library.embedded is self

    async def tool_snapshot(self):
        try:
            await self.flush()
        except ValueError as error:
            if self.tools_current():
                self.library.notice.text = str(error)
            return None
        return self.text if self.tools_current() else None

    async def replace_draft(self, original, updated):
        if not self.tools_current():
            return False
        await self.flush()
        if not self.tools_current() or self.text != original:
            raise ValueError('The draft changed. Reopen this tool before applying changes.')
        # Apply through Source so protected blocks and YAML retain exact syntax.
        if not await self.choose_mode(False):
            return False
        if not self.tools_current() or self.text != original:
            return False
        self.source.value = updated
        self.changed(updated)
        return True

    async def show_contents(self, widget=None, **kwargs):
        from markdown_it import MarkdownIt
        text = await self.tool_snapshot()
        if text is None:
            return
        parts = split_frontmatter(text)
        offset = len(parts.prefix)
        lines = parts.body.splitlines(keepends=True)
        tokens = MarkdownIt('commonmark').parse(parts.body)
        headings = [(tokens[index + 1].content, offset + sum(map(len, lines[:token.map[0]])))
                    for index, token in enumerate(tokens) if token.type == 'heading_open']
        if not headings:
            self.library.notice.text = 'This document has no headings.'
            return
        dialog = DocumentTypeDialog(choices=[(title, str(index)) for index, (title, _) in enumerate(headings)])
        dialog.title, dialog.message = 'Contents', 'Jump to a heading in Source.'
        selected = await self.library.view.window.dialog(dialog)
        if self.tools_current() and self.text == text and selected in {str(i) for i in range(len(headings))}:
            if not await self.choose_mode(False):
                return
            if self.tools_current() and self.text == text:
                start = headings[int(selected)][1]
                select_source(self.source, start, start)

    async def show_find(self, widget=None, **kwargs):
        from commonUtils.ui.native.editor_search import EditorSearch
        if not await self.choose_mode(False):
            return
        if not self.tools_current():
            return
        if not hasattr(self, 'finder'):
            self.finder = EditorSearch(self.source, self.view, insertion_index=0)
        if self.finder.box not in self.view.children:
            self.finder.toggle()
        self.finder.query.focus()

    async def show_properties(self, widget=None, **kwargs):
        original = await self.tool_snapshot()
        if original is None:
            return
        try:
            properties = parse_properties(split_frontmatter(original))
        except ValueError as error:
            self.library.notice.text = str(error)
            return await self.edit_yaml()
        rows = toga.Box(style=Pack(direction=COLUMN))
        for name, value in properties.items():
            async def edit(widget=None, name=name, value=value, **kw):
                if isinstance(value, RawYAML) or isinstance(value, list) and any(not isinstance(item, str) for item in value):
                    return await self.edit_yaml()
                self.property_form(original, name, value)
            button = toga.Button(shorten(f'{name}: {value}', width=36, placeholder='…'),
                                 on_press=edit, style=Pack(height=48))
            button.accessible_name = f'{name}: {value}'
            rows.add(button)
        rows.add(toga.Button('Add property…', on_press=lambda w: self.property_form(original), style=Pack(height=48)),
            toga.Button('Edit YAML…', on_press=self.edit_yaml, style=Pack(height=48)),
            toga.Button('Done', on_press=lambda w: self.library.present(), style=Pack(height=48)))
        self.show_tool('Properties', rows)

    def show_tool(self, title, content):
        if not self.tools_current():
            return
        for previous in getattr(self, 'tool_views', ()):
            clear_tool(previous)
        self.tool_views = [content]
        self.library.host.show_view(toga.Box(children=[toga.Label(title, style=Pack(font_size=20)),
            toga.ScrollContainer(content=content, horizontal=False, style=Pack(flex=1))],
            style=Pack(direction=COLUMN, flex=1, margin=12)), destination=self.library.destination,
            route='notes-properties', title=title)

    def property_form(self, original, name='', value=''):
        field = toga.TextInput(value=name, readonly=bool(name), placeholder='Property name', style=Pack(height=48))
        types = ['Text', 'Number', 'Checkbox', 'Date', 'Date & time', 'List', 'Tags']
        kind = ('Checkbox' if isinstance(value, bool) else 'Date & time' if isinstance(value, datetime)
                else 'Date' if isinstance(value, date) else 'Number' if isinstance(value, (int, float))
                else 'List' if isinstance(value, list) else 'Text')
        selection = toga.Selection(items=types, value=kind, style=Pack(height=48))
        text = ('\n'.join(map(str, value)) if isinstance(value, list) else
                str(value).lower() if isinstance(value, bool) else str(value))
        entry = toga.MultilineTextInput(value=text, style=Pack(height=140))
        status = toga.Label('Lists: one item per line.\nComplex values: Edit YAML.', style=Pack(font_size=12))
        async def apply(widget=None, *, remove=False, **kwargs):
            try:
                if not name and field.value in parse_properties(split_frontmatter(original)):
                    raise ValueError('That property already exists. Edit its existing row.')
                selected, raw = selection.value, entry.value
                parsed = raw
                if not remove:
                    if selected in ('List', 'Tags'):
                        parsed = [line for line in raw.splitlines() if line.strip()]
                    elif selected == 'Checkbox':
                        if raw.strip().lower() not in ('true', 'false'):
                            raise ValueError('A checkbox value must be true or false.')
                        parsed = raw.strip().lower() == 'true'
                    elif selected == 'Number':
                        parsed = parse_property_value(raw)
                        if isinstance(parsed, bool) or not isinstance(parsed, (int, float)):
                            raise ValueError('Enter a literal number.')
                    elif selected == 'Date':
                        parsed = date.fromisoformat(raw.strip())
                    elif selected == 'Date & time':
                        parsed = datetime.fromisoformat(raw.strip())
                updated = replace_property(original, name or field.value, parsed, remove=remove)
                if await self.replace_draft(original, updated):
                    self.library.present()
            except ValueError as error:
                status.text = fill(str(error), width=36)
        rows = toga.Box(children=[field, selection, entry, status,
            toga.Button('Apply', on_press=apply, style=Pack(height=48))], style=Pack(direction=COLUMN))
        if name:
            rows.add(toga.Button('Remove property', on_press=lambda w: apply(remove=True), style=Pack(height=48)))
        rows.add(toga.Button('Cancel', on_press=lambda w: self.library.present(), style=Pack(height=48)))
        self.show_tool('Edit property' if name else 'Add property', rows)

    async def edit_yaml(self, widget=None, **kwargs):
        original = await self.tool_snapshot()
        if original is None:
            return
        source = toga.MultilineTextInput(value=split_frontmatter(original).yaml_text, style=Pack(height=240))
        status = toga.Label('Edit YAML properties.\nThe document body is preserved.', style=Pack(font_size=12))
        async def apply(widget=None, **kwargs):
            try:
                if await self.replace_draft(original, replace_frontmatter(original, source.value)):
                    self.library.present()
            except ValueError as error:
                status.text = fill(str(error), width=36)
        self.show_tool('Edit YAML', toga.Box(children=[source, status,
            toga.Button('Apply', on_press=apply, style=Pack(height=48)),
            toga.Button('Cancel', on_press=lambda w: self.library.present(), style=Pack(height=48))],
            style=Pack(direction=COLUMN)))
