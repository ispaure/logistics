"""Inert offline EPUB HTML for mobile WebViews."""
import base64
from html import escape
from xml.etree import ElementTree as ET
from features.books.epub import resolve_href
from features.comics.mobile.validation import image_dimensions


def chapter_html(book, index, font_size=16, *, margin=16, theme='system'):
    if not 0 <= index < len(book.spine):
        raise IndexError('Chapter does not exist.')
    size = int(font_size)
    if not 12 <= size <= 32:
        raise ValueError('Invalid reading font size.')
    if margin not in (8, 16, 24, 32) or theme not in ('system', 'light', 'dark'):
        raise ValueError('Invalid reader appearance.')
    path = book.spine[index]
    source = book.read(path)
    if len(source) > 2 * 1024 * 1024:
        raise ValueError('Mobile EPUB chapters are limited to 2 MiB.')
    root = ET.fromstring(source)
    body = next((node for node in root.iter() if isinstance(node.tag, str)
                 and node.tag.rsplit('}', 1)[-1].lower() == 'body'), root)
    allowed = {'p', 'div', 'span', 'section', 'article', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
               'strong', 'b', 'em', 'i', 'u', 's', 'blockquote', 'pre', 'code', 'ul', 'ol', 'li',
               'table', 'thead', 'tbody', 'tr', 'th', 'td', 'sup', 'sub', 'br', 'hr'}
    blocked = {'head', 'script', 'style', 'iframe', 'object', 'embed', 'svg', 'math',
               'form', 'input', 'button', 'textarea', 'link', 'meta', 'base', 'video', 'audio'}
    images = 0
    def render(node, depth=0):
        nonlocal images
        if depth > 64:
            raise ValueError('EPUB chapter nesting exceeds the mobile limit.')
        if not isinstance(node.tag, str):
            return ''
        tag = node.tag.rsplit('}', 1)[-1].lower()
        if tag in blocked:
            return ''
        if tag == 'img':
            try:
                resource, _ = resolve_href(path, node.get('src', ''))
                if resource not in book.members or book.resource_sizes[resource] > 256 * 1024:
                    raise ValueError('Large image')
                data = book.read(resource)
                image_dimensions(data)
                images += len(data)
                if images > 1024 * 1024:
                    raise ValueError('Image budget')
                mime = ('image/png' if data.startswith(b'\x89PNG') else
                        'image/webp' if data[:4] == b'RIFF' else 'image/jpeg')
                return f'<img alt="{escape(node.get("alt", ""), quote=True)}" src="data:{mime};base64,{base64.b64encode(data).decode()}">'
            except (ValueError, KeyError):
                return '<span>[Image omitted: unsupported or too large]</span>'
        text = escape(node.text or '')
        for child in node:
            text += render(child, depth + 1) + escape(child.tail or '')
        if tag in {'br', 'hr'}:
            return '<' + tag + '>'
        return '<' + tag + '>' + text + '</' + tag + '>' if tag in allowed else text
    content = render(body)
    result = ('<!doctype html><html><head><meta charset="utf-8">'
              '<meta name="viewport" content="width=device-width, initial-scale=1">'
              '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
              f'<style>html{{color-scheme:{"light dark" if theme == "system" else theme}}}body{{background:Canvas;color:CanvasText;font:{size}px system-ui;line-height:1.5;margin:{margin}px;overflow-wrap:anywhere}}'
              'img{max-width:100%;height:auto}pre{white-space:pre-wrap}table{max-width:100%}</style>'
              '</head><body>' + content + '</body></html>')
    if len(result.encode('utf-8')) > 2 * 1024 * 1024:
        raise ValueError('Rendered chapter exceeds the mobile 2 MiB limit.')
    return result
