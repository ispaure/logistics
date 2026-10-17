"""Offline formatted Markdown input; untouched blocks retain their exact source."""
from html import escape
import json
import re
from urllib.parse import urlsplit, parse_qs
from uuid import uuid4

import toga
from toga.style import Pack
from markdown_it import MarkdownIt
from commonUtils.ui.appearance.formatting_glyphs import formatting_svg


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
        result.append(dict(source=source, editable=editable, html=rendered))
        cursor = end
    if cursor < len(lines):
        result.append(dict(source=''.join(lines[cursor:]), editable=False, html=''))
    # A trailing blank paragraph also permits appending after protected syntax.
    result.append(dict(source='', editable=True, html='<p><br></p>'))
    return result


_SCRIPT = r'''
const blocks = DATA;
const root = document.getElementById('document');
function tableBoundaries(section) {
    if (!section.querySelector('table')) return;
    const boundary = () => {
        const p = document.createElement('p'); p.dataset.editorBoundary = 'true'; p.innerHTML = '<br>'; return p;
    };
    if (section.firstElementChild?.nodeName === 'TABLE') section.prepend(boundary());
    if (section.lastElementChild?.nodeName === 'TABLE') section.append(boundary());
}
for (const [index, block] of blocks.entries()) {
    const section = document.createElement('section');
    section.dataset.index = index;
    section.innerHTML = block.html;
    tableBoundaries(section);
    section.contentEditable = block.editable ? 'true' : 'false';
    if (!block.editable && block.html) {
        section.title = 'Edit this block in Source mode';
        section.dataset.sourceOnly = 'true';
    }
    root.append(section);
    block.originalHTML = section.innerHTML;
}
function inline(node) {
    if (node.nodeType === Node.TEXT_NODE)
        return node.data.replace(/\\/g, '\\\\').replace(/([*_`\[\]<>])/g, '\\$1');
    if (node.dataset && node.dataset.markdown) return node.dataset.markdown;
    const text = Array.from(node.childNodes, inline).join('');
    switch (node.nodeName) {
    case 'STRONG': case 'B': return '**' + text + '**';
    case 'EM': case 'I': return '*' + text + '*';
    case 'S': case 'STRIKE': case 'DEL': return '~~' + text + '~~';
    case 'CODE': {
        const raw = node.textContent;
        const fence = '`'.repeat(Math.max(0, ...Array.from(raw.matchAll(/`+/g), m => m[0].length)) + 1);
        return fence + ' ' + raw + ' ' + fence;
    }
    case 'BR': return '\n';
    case 'A': {
        const href = (node.getAttribute('href') || '').replace(/\(/g, '%28').replace(/\)/g, '%29');
        const title = node.getAttribute('title');
        return '[' + text + '](' + href + (title ? ' "' + title.replace(/"/g, '\\"') + '"' : '') + ')';
    }
    case 'SPAN': {
        let styled = text;
        if (node.style.fontWeight === 'bold' || Number(node.style.fontWeight) >= 600) styled = '**' + styled + '**';
        if (node.style.fontStyle === 'italic') styled = '*' + styled + '*';
        if (node.style.textDecoration.includes('line-through')) styled = '~~' + styled + '~~';
        return styled;
    }
    case 'DIV': return '\n' + text;
    // Native editing engines can introduce extra wrappers. Retain their text
    // even when their visual style has no Markdown equivalent.
    default: return text;
    }
}
function serialize(node) {
    if (node.nodeType === Node.TEXT_NODE) return inline(node);
    const children = () => Array.from(node.childNodes, serialize).join('');
    switch (node.nodeName) {
    case 'SECTION': {
        let result = '', run = '';
        const flush = () => {if (run.trim()) result += run.trim() + '\n\n'; run = '';};
        for (const child of node.childNodes) {
            if (/^(P|DIV|H[1-6]|UL|OL|PRE|BLOCKQUOTE|TABLE)$/.test(child.nodeName)) {
                flush(); result += serialize(child);
            } else if (child.nodeType !== Node.TEXT_NODE || child.data.trim()) run += inline(child);
        }
        flush();
        return result;
    }
    case 'DIV':
        if (node.className === 'table-scroll') return children();
        return Array.from(node.childNodes, inline).join('').trimEnd() + '\n\n';
    case 'P':
        if (node.dataset.editorBoundary && !node.textContent) return '';
        return Array.from(node.childNodes, inline).join('').trimEnd() + '\n\n';
    case 'H1': case 'H2': case 'H3': case 'H4': case 'H5': case 'H6':
        return '#'.repeat(Number(node.nodeName[1])) + ' ' + Array.from(node.childNodes, inline).join('') + '\n\n';
    case 'BLOCKQUOTE': return children().trimEnd().split('\n').map(s => '> ' + s).join('\n') + '\n\n';
    case 'TABLE': {
        const rows = Array.from(node.rows, row => Array.from(row.cells, cell =>
            Array.from(cell.childNodes, inline).join('').replace(/\|/g, '\\|').replace(/\n/g, '<br>')));
        if (!rows.length) return '';
        return '| ' + rows[0].join(' | ') + ' |\n| ' + rows[0].map(() => '---').join(' | ') + ' |\n'
            + rows.slice(1).map(row => '| ' + row.join(' | ') + ' |').join('\n') + '\n\n';
    }
    case 'UL': case 'OL': {
        const start = Number(node.getAttribute('start') || 1);
        return Array.from(node.children, (li, i) => {
            const value = Array.from(li.childNodes, child =>
                ['UL','OL'].includes(child.nodeName) ? '\n' + serialize(child) :
                ['P','DIV'].includes(child.nodeName) ? serialize(child) : inline(child)).join('').trimEnd();
            const marker = node.nodeName === 'OL' ? (start+i)+'. ' : '- ';
            return marker + value.split('\n').join('\n' + ' '.repeat(marker.length));
        }).join('\n') + '\n\n';
    }
    case 'PRE': {
        const raw = node.textContent.replace(/\n$/, '');
        const fence = '`'.repeat(Math.max(2, ...Array.from(raw.matchAll(/`+/g), m => m[0].length)) + 1);
        const code = node.querySelector('code');
        const language = code && (code.className.match(/language-([\w+-]+)/) || [,''])[1] || '';
        return fence + language + '\n' + raw + '\n' + fence + '\n\n';
    }
    default: return inline(node);
    }
}
function publish() {
    try {
        const parts = [];
        const text = Array.from(root.children, section => {
            const block = blocks[Number(section.dataset.index)];
            if (section.innerHTML === block.originalHTML) {parts.push(block.source); return block.source;}
            let edited = serialize(section).replace(/\n+$/, '');
            const ending = block.source.match(/\n*$/)[0];
            const previous = parts.join('');
            const prefix = block.source === '' && previous ? (previous.endsWith('\n\n') ? '' : previous.endsWith('\n') ? '\n' : '\n\n') : '';
            const result = prefix + edited + (ending || '\n\n');
            parts.push(result);
            return result;
        }).join('');
        if (new TextEncoder().encode(text).length > 1024 * 1024)
            throw Error('Formatted editing is limited to 1 MiB.');
        location.href = BRIDGE + '?text=' + encodeURIComponent(text);
        document.getElementById('notice').textContent = '';
    } catch (error) {
        document.getElementById('notice').textContent = error.message + ' Undo this change before switching modes.';
    }
}
root.addEventListener('input', event => {if (!event.isComposing) publish();});
root.addEventListener('compositionend', publish);
root.addEventListener('paste', event => {
    event.preventDefault();
    document.execCommand('insertText', false, event.clipboardData.getData('text/plain'));
});
let savedRange = null;
function editableRange(range) {
    const element = node => node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
    const first = element(range.startContainer)?.closest('section[contenteditable=true]');
    const last = element(range.endContainer)?.closest('section[contenteditable=true]');
    return first && first === last && root.contains(first);
}
document.addEventListener('selectionchange', () => {
    const selection = getSelection();
    if (root.contains(document.activeElement) && selection.rangeCount && editableRange(selection.getRangeAt(0))) savedRange = selection.getRangeAt(0).cloneRange();
});
function restoreRange() {
    const selection = getSelection();
    if (root.contains(document.activeElement) && selection.rangeCount && editableRange(selection.getRangeAt(0)))
        savedRange = selection.getRangeAt(0).cloneRange();
    if (!savedRange || !editableRange(savedRange)) {
        savedRange = document.createRange();
        savedRange.selectNodeContents(root.querySelector('section[contenteditable=true]'));
        savedRange.collapse(false);
    }
    const range = savedRange.cloneRange();
    const container = range.commonAncestorContainer;
    const element = container.nodeType === Node.ELEMENT_NODE ? container : container.parentElement;
    element.closest('section[contenteditable=true]').focus({preventScroll:true});
    selection.removeAllRanges();
    selection.addRange(range);
    savedRange = range.cloneRange();
    return selection;
}
document.querySelector('nav').addEventListener('pointerdown', () => {
    const selection = getSelection();
    if (root.contains(document.activeElement) && selection.rangeCount && editableRange(selection.getRangeAt(0))) savedRange = selection.getRangeAt(0).cloneRange();
}, true);
function command(name, value=null) {
    restoreRange();
    document.execCommand(name, false, value);
    publish();
}
document.querySelectorAll('[data-command]').forEach(button => {
    button.addEventListener('mousedown', event => event.preventDefault());
    button.addEventListener('click', () => command(button.dataset.command, button.dataset.value || null));
});
document.getElementById('block-style').addEventListener('change', event => {
    command('formatBlock', event.target.value);
    event.target.value = '';
});
document.getElementById('inline-code').addEventListener('click', () => {
    const selection = restoreRange();
    const code = document.createElement('code');
    code.textContent = selection.toString() || 'code';
    command('insertHTML', code.outerHTML);
});
document.getElementById('apply-link').addEventListener('click', () => {
    const href = document.getElementById('link-target').value.trim().replace(/ /g, '%20');
    if (!href || /[\x00-\x20<>]/.test(href) || href.startsWith('//') ||
        (/^[\w+.-]+:/.test(href) && !/^(https?:|mailto:)/i.test(href))) {
        document.getElementById('notice').textContent = 'Enter a relative file path, https:// address or mailto: link.';
        return;
    }
    const selection = restoreRange();
    if (selection.isCollapsed) {
        const anchor = document.createElement('a');
        anchor.setAttribute('href', href);
        anchor.textContent = 'Link';
        command('insertHTML', anchor.outerHTML);
    } else command('createLink', href);
});
function tableCommand(action) {
    const selection = restoreRange();
    if (action === 'insert') {
        command('insertHTML', '<table><thead><tr><th>Header</th><th>Header</th></tr></thead><tbody><tr><td>Cell</td><td>Cell</td></tr></tbody></table><p><br></p>');
        return;
    }
    const node = selection.anchorNode;
    const element = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
    const cell = element.closest('td,th'), table = element.closest('table');
    if (!table || !cell) {
        document.getElementById('notice').textContent = 'Place the cursor in a table cell first.';
        return;
    }
    const clone = table.cloneNode(true), row = cell.parentElement.rowIndex, column = cell.cellIndex;
    if (action === 'row') {
        const added = clone.insertRow(row+1);
        for (let index=0; index<table.rows[row].cells.length; index++) added.insertCell().textContent = 'Cell';
    } else if (action === 'column') {
        for (const existing of clone.rows) {
            const added = document.createElement(existing.rowIndex === 0 ? 'th' : 'td');
            added.textContent = existing.rowIndex === 0 ? 'Header' : 'Cell';
            existing.insertBefore(added, existing.cells[column+1] || null);
        }
    } else if (action === 'delete-row') clone.deleteRow(row);
    else if (action === 'delete-column') for (const existing of clone.rows) existing.deleteCell(column);
    // WebKit canonicalizes a bare table selection into its first cell. Replace
    // the enclosing editing block between real paragraph caret positions.
    const section = table.closest('section');
    tableBoundaries(section);
    const replacement = section.cloneNode(true);
    const index = Array.from(section.querySelectorAll('table')).indexOf(table);
    const result = clone.rows.length && clone.rows[0].cells.length ? clone : document.createElement('p');
    if (!result.hasChildNodes()) result.innerHTML = '<br>';
    replacement.querySelectorAll('table')[index].replaceWith(result);
    const range = document.createRange();
    range.selectNodeContents(section);
    selection.removeAllRanges(); selection.addRange(range);
    savedRange = range.cloneRange();
    // A single native replacement keeps structural table edits undoable.
    document.execCommand('insertHTML', false, replacement.innerHTML);
    publish();
}
document.querySelectorAll('[data-table]').forEach(button => {
    button.addEventListener('mousedown', event => event.preventDefault());
    button.addEventListener('click', () => tableCommand(button.dataset.table));
});
'''


def editor_html(text, bridge, font_size=16, *, image_source=None):
    nonce = uuid4().hex
    data = json.dumps(editor_blocks(text, image_source=image_source), ensure_ascii=True).replace('<', '\\u003c')
    script = _SCRIPT.replace('location.href = BRIDGE', 'location.href = ' + json.dumps(bridge)).replace('const blocks = DATA;', 'const blocks = ' + data + ';')
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
    style_menu = '<label>Block <select id="block-style" aria-label="Block style"><option value="" selected disabled>Choose style…</option>' + ''.join(
        f'<option value="{value}">{name}</option>' for name, value in styles) + '</select></label>'
    tables = [('Insert table', 'insert'), ('Add row', 'row'), ('Add column', 'column'),
              ('Delete row', 'delete-row'), ('Delete column', 'delete-column')]
    table_glyphs = {'insert': 'table', 'row': 'row_add', 'column': 'column_add',
                    'delete-row': 'row_delete', 'delete-column': 'column_delete'}
    table_menu = ''.join(icon_button(name, table_glyphs[action], f'data-table="{action}"') for name, action in tables)
    toolbar = buttons(common) + '<details><summary aria-label="Markdown formatting" title="Markdown formatting">' + formatting_svg('format') + '</summary><div class="format-menu">' + style_menu + buttons(more) + (
        icon_button('Inline code', 'code', 'id="inline-code"') +
        '<label>Link <input id="link-target" type="text" placeholder="https://… or relative file" aria-label="Link destination"></label>' +
        icon_button('Apply link', 'link', 'id="apply-link"')) + table_menu + '</div></details>'
    return (f'<!doctype html><html><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            f'script-src \'nonce-{nonce}\'; style-src \'unsafe-inline\'; img-src data:; base-uri \'none\'; form-action \'none\'">'
            f'<style>:root{{color-scheme:light dark}}body{{font:{int(font_size)}px/1.6 system-ui;'
            'margin:12px;background:Canvas;color:CanvasText;overflow-wrap:anywhere}'
            'nav{position:sticky;top:0;background:Canvas;z-index:1;display:flex;flex-wrap:wrap;gap:4px}'
            'button,select,input,summary{min-height:44px;box-sizing:border-box}select,input{font:inherit;max-width:100%}'
            'summary{display:flex;align-items:center;justify-content:center;width:44px;padding:0;cursor:pointer;list-style:none}summary::-webkit-details-marker{display:none}.icon-button{width:44px;padding:0;display:inline-flex;align-items:center;justify-content:center}.icon-button svg,summary svg{pointer-events:none}.format-menu{display:flex;flex-wrap:wrap;gap:4px;padding:8px 0}.format-menu label{max-width:100%}'
            'button{min-height:44px;font:inherit;color:CanvasText;background:Canvas;border:1px solid GrayText;border-radius:6px}'
            'p[data-editor-boundary]{margin:0;line-height:.5em;min-height:.5em}section{outline:none;min-height:1em}section:empty{display:none}section[contenteditable=true]:focus{outline:1px solid Highlight}'
            'section[contenteditable=false]{opacity:.8}section[data-source-only]::after{content:"Edit this block in Source";display:block;font-size:.8em;color:GrayText}pre{white-space:pre-wrap}blockquote{border-left:3px solid GrayText;padding-left:1em}'
            'table{border-collapse:collapse;max-width:100%;display:block;overflow-x:auto}td,th{border:1px solid GrayText;padding:4px}#notice{color:MarkText;background:Mark}'
            '</style></head><body><nav aria-label="Markdown formatting">' + toolbar + '</nav>'
            '<p id="notice" role="status"></p><main id="document" aria-label="Formatted Markdown editor"></main>'
            f'<script nonce="{nonce}">{script}</script></body></html>')


class FormattedMarkdownInput:
    def __init__(self, changed, *, font_size=16, image_source=None):
        self.changed, self.font_size = changed, font_size
        self.image_source = image_source
        self.closed = False
        self.text = None
        self.bridge = 'logistics-editor://' + uuid4().hex + '/'
        self.view = toga.WebView(on_navigation_starting=self.navigate, style=Pack(flex=1))

    def load(self, text):
        if self.closed or self.text == text:
            return
        bridge = 'logistics-editor://' + uuid4().hex + '/'
        content = editor_html(text, bridge, self.font_size,
            image_source=self.image_source() if self.image_source else None)
        self.bridge = bridge
        self.text = text
        self.view.set_content('https://logistics.invalid/' + uuid4().hex + '/', content)

    def navigate(self, widget, url, **kwargs):
        if not self.closed and url.split('?', 1)[0] == self.bridge:
            values = parse_qs(urlsplit(url).query, keep_blank_values=True)
            if set(values) == {'text'} and len(values['text']) == 1:
                text = values['text'][0]
                if len(text.encode('utf-8')) <= 1024 * 1024 and text != self.text:
                    self.text = text
                    self.changed(text)
        return False

    def dispose(self):
        self.closed = True
        self.changed = None
        self.image_source = None
        retire_webview(self.view)


def retire_webview(view):
    native = getattr(view._impl, 'native', None)
    if type(view._impl).__module__.startswith('toga_iOS.') and native is not None:
        native.stopLoading()
        native.navigationDelegate = None
        native.UIDelegate = None
    view.set_content('https://logistics.invalid/closed/', '<p>Document closed.</p>')
