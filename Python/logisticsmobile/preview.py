"""Bounded, offline Markdown preview without active HTML or external resources."""
from html import escape
import re
from .palette import css_variables


def markdown_body(text):
    """Render inert basic Markdown for local document and conversation views."""
    if len(text.encode('utf-8')) > 1024 * 1024:
        raise ValueError('Preview is limited to 1 MiB.')
    output, code, listing = [], False, None
    def inline(value):
        value = escape(value)
        value = re.sub(r'`([^`\n]+)`', r'<code>\1</code>', value)
        value = re.sub(r'\*\*([^*\n]+)\*\*', r'<strong>\1</strong>', value)
        return value
    for line in text.splitlines():
        item = re.match(r'^\s*(?:([-*])\s+|\d+[.)]\s+)(.*)$', line) if not code else None
        kind = ('ul' if item[1] else 'ol') if item else None
        if listing and kind != listing:
            output.append(f'</{listing}>')
            listing = None
        if line.startswith('```'):
            output.append('</code></pre>' if code else '<pre><code>')
            code = not code
        elif code:
            output.append(escape(line) + '\n')
        else:
            heading = re.match(r'^(#{1,6})\s+(.*)$', line)
            if heading:
                level = len(heading[1])
                output.append(f'<h{level}>{inline(heading[2])}</h{level}>')
            elif item:
                if listing is None:
                    output.append(f'<{kind}>')
                    listing = kind
                output.append('<li>' + inline(item[2]) + '</li>')
            elif line.strip():
                output.append('<p>' + inline(line) + '</p>')
            else:
                output.append('<br>')
    if code:
        output.append('</code></pre>')
    if listing:
        output.append(f'</{listing}>')
    return ''.join(output)


def markdown_preview(text, font_size=16):
    size = int(font_size)
    if not 12 <= size <= 32:
        raise ValueError('Invalid preview font size.')
    body = markdown_body(text)
    policy = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
    result = ('<!doctype html><html><head><meta charset="utf-8">'
            f'<meta http-equiv="Content-Security-Policy" content="{policy}">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<style>{css_variables()}body{{background:var(--surface);color:var(--text);font: {size}px system-ui;margin:16px;overflow-wrap:anywhere}}'
            'pre{white-space:pre-wrap}code{font-family:monospace}</style></head><body>'
            + body + '</body></html>')
    if len(result.encode('utf-8')) > 2 * 1024 * 1024:
        raise ValueError('The rendered preview exceeds 2 MiB; preview a smaller document.')
    return result
