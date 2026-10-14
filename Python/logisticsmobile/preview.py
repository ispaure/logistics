"""Bounded, offline Markdown preview without active HTML or external resources."""
from html import escape
import re


def markdown_preview(text, font_size=16):
    if len(text.encode('utf-8')) > 1024 * 1024:
        raise ValueError('Preview is limited to 1 MiB.')
    size = int(font_size)
    if not 12 <= size <= 32:
        raise ValueError('Invalid preview font size.')
    output, code = [], False
    def inline(value):
        value = escape(value)
        value = re.sub(r'`([^`\n]+)`', r'<code>\1</code>', value)
        value = re.sub(r'\*\*([^*\n]+)\*\*', r'<strong>\1</strong>', value)
        return value
    for line in text.splitlines():
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
            elif line.startswith(('- ', '* ')):
                output.append('<div>• ' + inline(line[2:]) + '</div>')
            elif line.strip():
                output.append('<p>' + inline(line) + '</p>')
            else:
                output.append('<br>')
    if code:
        output.append('</code></pre>')
    policy = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
    result = ('<!doctype html><html><head><meta charset="utf-8">'
            f'<meta http-equiv="Content-Security-Policy" content="{policy}">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<style>html{{color-scheme:light dark}}body{{background:Canvas;color:CanvasText;font: {size}px system-ui;margin:16px;overflow-wrap:anywhere}}'
            'pre{white-space:pre-wrap}code{font-family:monospace}</style></head><body>'
            + ''.join(output) + '</body></html>')
    if len(result.encode('utf-8')) > 2 * 1024 * 1024:
        raise ValueError('The rendered preview exceeds 2 MiB; preview a smaller document.')
    return result
