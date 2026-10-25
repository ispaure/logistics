"""Offline formatted Markdown input; untouched blocks retain their exact source."""
from html import escape
import json
import math
import re
from urllib.parse import urlsplit, parse_qs
from uuid import uuid4

import toga
from toga.style import Pack
from markdown_it import MarkdownIt
from commonUtils.ui.appearance.formatting_glyphs import formatting_svg
from commonUtils.formats.markdown.editing import web_patterns
from .markdown_script import SCRIPT as _SCRIPT
from .markdown_live_script import LIVE_SCRIPT
from .markdown_style import EDITOR_CSS
from services.documents.mobile_views import retire_webview


def editor_blocks(text, *, image_source=None):
    """Map top-level CommonMark blocks to source, including invisible syntax.

    Complex syntax remains read-only in formatted mode. Source mode always owns
    the complete original text; merely entering/leaving formatted mode is lossless.
    """
    if len(text.encode('utf-8')) > 1024 * 1024:
        raise ValueError('Formatted editing is limited to 1 MiB. Use Source mode.')
    # CommonMark counts CR/LF lines; Unicode paragraph separators are text.
    lines = re.split(r'(?<=\n)|(?<=\r)(?!\n)', text)
    if lines and not lines[-1]:
        lines.pop()
    parser = MarkdownIt('commonmark', {'html': False}).enable(['table', 'strikethrough'])
    render_fence = parser.renderer.rules['fence']
    def fence(renderer, items, index, options, env):
        token = items[index]
        metadata = ('<pre data-markdown-info="' + escape(token.info, quote=True)
                    + '" data-markdown-fence="' + escape(token.markup, quote=True) + '">')
        return render_fence(items, index, options, env).replace('<pre>', metadata, 1)
    parser.add_render_rule('fence', fence)
    from commonUtils.ui.native.markdown_preview import embedded_image, wiki_image
    if image_source is not None:
        parser.inline.ruler.before('image', 'wiki_image', wiki_image)
    def image(renderer, items, index, options, env):
        token = items[index]
        title = token.attrGet('title')
        suffix = (' \"' + title.replace('\"', '\\\"') + '\"') if title else ''
        original = '![' + token.content + '](' + (token.attrGet('src') or '') + suffix + ')'
        return '<span contenteditable="false" data-markdown="' + escape(original, quote=True) + '">' + embedded_image(token.attrGet('src') or '', token.content or 'Image', image_source) + '</span>'
    parser.add_render_rule('image', image)
    ranges = []
    frontmatter = 0
    if lines and lines[0].strip() == '---':
        for index, line in enumerate(lines[1:], 1):
            if line.strip() in ('---', '...'):
                frontmatter = index + 1
                ranges.append((0, frontmatter, False))
                break
    body = ''.join(lines[frontmatter:])
    for token in parser.parse(body):
        if token.level == 0 and token.map is not None and token.type != 'inline':
            start, end = (n + frontmatter for n in token.map)
            if ranges and start < ranges[-1][1]:
                continue
            source = ''.join(lines[start:end])
            # Wiki aliases and embedded HTML retain exact spelling in Source mode.
            safe = (token.type in ('paragraph_open', 'heading_open', 'blockquote_open',
                                  'bullet_list_open', 'ordered_list_open', 'fence', 'code_block', 'table_open')
                    and not re.search(r'\[\[|<|\$|^\s*\[[^]]+\]:', source, re.M)
                    and not re.search(r'\][ \t]*\[|\[[^]\n]+\](?![([])', source))
            if token.type in ('fence', 'code_block'):
                safe = True
            ranges.append((start, end, safe))
    result, cursor = [], 0
    for start, end, editable in ranges:
        if start > cursor:
            result.append(dict(source=''.join(lines[cursor:start]), editable=False, html=''))
        source = ''.join(lines[start:end])
        rendered = parser.render(source) if start >= frontmatter else '<pre>' + escape(source) + '</pre>'
        tokens = parser.parse(source) if editable else []
        if (len(tokens) == 3 and tokens[0].type in ('paragraph_open', 'heading_open')
                and all(child.type in ('text', 'strong_open', 'strong_close', 'em_open',
                                       'em_close', 'code_inline') for child in (tokens[1].children or []))
                and '\n' not in tokens[1].content and '\\' not in source
                and not re.search(r'&(?:#\w+|\w+);', source)
                and not (tokens[0].type == 'heading_open' and not source.startswith('#'))):
            # Keep delimiters in the editable DOM just as Qt does. The original
            # source remains the no-op baseline, including trailing newlines.
            raw = source.rstrip('\r\n')
            rendered = '<p><span data-live-source="">' + escape(raw) + '</span></p>'
        result.append(dict(source=source, editable=editable, html=rendered))
        cursor = end
    if cursor < len(lines):
        result.append(dict(source=''.join(lines[cursor:]), editable=False, html=''))
    # A trailing blank paragraph also permits appending after protected syntax.
    result.append(dict(source='', editable=True, html='<p><br></p>'))
    return result





def editor_html(text, bridge, font_size=16, *, image_source=None, stylesheet=''):
    nonce = uuid4().hex
    data = json.dumps(editor_blocks(text, image_source=image_source), ensure_ascii=True).replace('<', '\\u003c')
    script = (_SCRIPT + LIVE_SCRIPT).replace('LIVE_ACTIVE', web_patterns()['active']).replace('LIVE_PATTERNS', json.dumps(web_patterns())).replace('location.href = BRIDGE', 'location.href = ' + json.dumps(bridge)).replace('const blocks = DATA;', 'const blocks = ' + data + ';')
    common = [('Bold', 'bold', ''), ('Italic', 'italic', ''), ('Undo', 'undo', ''), ('Redo', 'redo', '')]
    more = [('Strike', 'strikeThrough', ''), ('Bullets', 'insertUnorderedList', ''),
            ('Numbered', 'insertOrderedList', ''), ('Remove link', 'unlink', '')]
    glyphs = {'bold': 'bold', 'italic': 'italic', 'undo': 'undo', 'redo': 'redo',
              'strikeThrough': 'strike', 'insertUnorderedList': 'bullets',
              'insertOrderedList': 'numbered', 'unlink': 'unlink'}
    def icon_button(name, glyph, attributes):
        return (f'<button type="button" class="icon-button" {attributes} '
                f'aria-label="{name}" title="{name}">{formatting_svg(glyph)}</button>')
    def buttons(items):
        return ''.join(icon_button(name, glyphs[cmd], f'data-command="{cmd}" data-value="{value}"')
                       for name, cmd, value in items)
    styles = [('Paragraph', 'p'), *[(f'Heading {level}', f'h{level}') for level in range(1, 7)],
              ('Quote', 'blockquote'), ('Code block', 'pre')]
    style_menu = '<label><span aria-hidden="true">Block</span> <select id="block-style" aria-label="Block style"><option value="" selected disabled>Choose style…</option>' + ''.join(
        f'<option value="{value}">{name}</option>' for name, value in styles) + '</select></label>'
    tables = [('Insert table', 'insert'), ('Add row', 'row'), ('Add column', 'column'),
              ('Delete row', 'delete-row'), ('Delete column', 'delete-column')]
    table_glyphs = {'insert': 'table', 'row': 'row_add', 'column': 'column_add',
                    'delete-row': 'row_delete', 'delete-column': 'column_delete'}
    table_menu = ''.join(icon_button(name, table_glyphs[action], f'data-table="{action}"') for name, action in tables)
    toolbar = '<span class="mode-label" aria-hidden="true">Formatted</span>' + buttons(common) + '<details><summary aria-label="Markdown formatting" title="Markdown formatting">' + formatting_svg('format') + '<span aria-hidden="true">Format</span></summary><div class="format-menu"><div class="compact-formatting">' + buttons(common) + '</div>' + style_menu + buttons(more) + (
        icon_button('Inline code', 'code', 'id="inline-code"') +
        icon_button('Insert link', 'link', 'id="show-link" aria-haspopup="dialog"')) + table_menu + '</div></details>'
    link_dialog = ('<dialog id="link-dialog" aria-labelledby="link-title">'
                   '<h2 id="link-title">Insert link</h2>'
                   '<div class="link-fields">'
                   '<label for="link-target">URL or file path</label>'
                   '<input id="link-target" type="text" inputmode="url" autocomplete="off" '
                   'autocapitalize="none" spellcheck="false" placeholder="https://… or relative file">'
                   '<p id="link-error" role="alert"></p></div><div class="dialog-actions">'
                   '<button type="button" id="cancel-link">Cancel</button>'
                   '<button type="button" id="apply-link">Insert link</button></div></dialog>')
    return (f'<!doctype html><html><head><meta charset="utf-8">'
            '<meta name="logistics-native-font" content="true">'
            '<meta name="viewport" content="width=device-width, initial-scale=1, interactive-widget=resizes-content">'
            f'<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            f'script-src \'nonce-{nonce}\'; style-src \'unsafe-inline\'; img-src data:; base-uri \'none\'; form-action \'none\'">'
            f'<style>body{{font-size:{int(font_size)}px}}' + EDITOR_CSS + stylesheet +
            '</style></head><body><nav aria-label="Markdown formatting">' + toolbar + '</nav>'
            '<p id="notice" role="status"></p><main id="document" aria-label="Formatted Markdown editor"></main>' + link_dialog +
            f'<script nonce="{nonce}">{script}</script></body></html>')


from services.documents.mobile_views import markdown_webview


class FormattedMarkdownInput:
    def __init__(self, changed, *, font_size=16, image_source=None, stylesheet='', private=False):
        self.changed, self.font_size = changed, font_size
        self.image_source = image_source
        self.stylesheet = stylesheet
        self.closed = False
        self.text = None
        self._blocks = ()
        self._revision = 0
        self.scroll_top = 0
        self.bridge = 'logistics-editor://' + uuid4().hex + '/'
        self.view = markdown_webview(private=private, on_navigation_starting=self.navigate,
                                    on_webview_load=self.loaded, style=Pack(flex=1))
        self._viewport_lock = None
        from commonUtils.ui.native.text_size import native_backend
        if native_backend(self.view).startswith('toga_android.'):
            from java import dynamic_proxy, jclass
            class ViewportLock(dynamic_proxy(jclass('android.view.View$OnScrollChangeListener'))):
                def onScrollChange(inner, native, x, y, old_x, old_y):
                    # Only the DOM writing pane scrolls. Older/vendor WebViews
                    # otherwise pan their entire viewport to reveal the caret,
                    # moving the formatting toolbar outside the visible area.
                    if x or y:
                        native.scrollTo(0, 0)
            self._viewport_lock = ViewportLock()
            self.view._impl.native.setOnScrollChangeListener(self._viewport_lock)

    async def loaded(self, widget=None, url=None, **kwargs):
        if not self.closed and self.scroll_top:
            await self.view.evaluate_javascript('(function(){const root=document.getElementById("document");'
                'if(root)root.scrollTop=' + json.dumps(self.scroll_top) + ';})()')

    def load(self, text):
        if self.closed or self.text == text:
            return
        bridge = 'logistics-editor://' + uuid4().hex + '/'
        content = editor_html(text, bridge, self.font_size,
            image_source=self.image_source() if self.image_source else None, stylesheet=self.stylesheet)
        self.bridge = bridge
        self._blocks = tuple(block['source'] for block in editor_blocks(text))
        self._revision = 0
        self.text = text
        self.view.set_content('https://logistics.invalid/' + uuid4().hex + '/', content)

    def navigate(self, widget, url, **kwargs):
        if not self.closed and url.split('?', 1)[0] == self.bridge:
            values = parse_qs(urlsplit(url).query, keep_blank_values=True)
            text = None
            if set(values) == {'patch'} and len(values['patch']) == 1:
                try:
                    raw = values['patch'][0]
                    if len(raw.encode('utf-8')) > 8 * 1024 * 1024:
                        return False
                    payload = json.loads(raw)
                    revision = payload['revision']
                    changes = payload['changes']
                    if type(revision) is not int or revision <= self._revision or not isinstance(changes, list):
                        return False
                    parts = list(self._blocks)
                    seen = set()
                    for index, source in changes:
                        if (type(index) is not int or index in seen or not 0 <= index < len(parts)
                                or not isinstance(source, str)):
                            return False
                        seen.add(index)
                        parts[index] = source
                    text = ''.join(parts)
                    if len(text.encode('utf-8')) > 1024 * 1024:
                        return False
                    self._revision = revision
                    scroll = payload.get('scroll')
                    if type(scroll) in (int, float) and math.isfinite(scroll):
                        self.scroll_top = min(1_000_000_000, max(0, scroll))
                except (ValueError, TypeError, KeyError):
                    return False
            elif set(values) == {'text'} and len(values['text']) == 1:
                text = values['text'][0]
            if text is not None and len(text.encode('utf-8')) <= 1024 * 1024 and text != self.text:
                self.text = text
                self.changed(text)
        return False

    async def flush(self):
        """Read pending DOM input before saving; failures keep the draft open."""
        from commonUtils.ui.native.text_size import native_backend
        if self.closed or not native_backend(self.view).startswith(('toga_iOS.', 'toga_android.')):
            return
        bridge = self.bridge
        raw = await self.view.evaluate_javascript('JSON.stringify(window.markdownSnapshot?.() ?? null)')
        if self.closed or bridge != self.bridge:
            raise ValueError('The Markdown editor closed before its edits could be saved.')
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict) or payload.get('revision', 0) <= self._revision:
                raise ValueError('Markdown input is not ready. Keep this note open and try again.')
            from urllib.parse import quote
            self.navigate(None, self.bridge + '?patch=' + quote(raw, safe=''))
            if self._revision != payload['revision']:
                raise ValueError('Markdown input could not be synchronized. Keep this note open.')
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError('Markdown input is not ready. Keep this note open and try again.') from error

    def dispose(self):
        self.closed = True
        self.changed = None
        self.text = None
        self._blocks = ()
        self.scroll_top = 0
        self.image_source = None
        if self._viewport_lock is not None:
            self.view._impl.native.setOnScrollChangeListener(None)
            self._viewport_lock = None
        retire_webview(self.view)
