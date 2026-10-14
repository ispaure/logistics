"""Safe mobile EPUB presentation and bounded native comic image inputs."""
import base64
from html import escape
import struct
from xml.etree import ElementTree as ET

from features.books.epub import resolve_href

MAX_IMAGE = 8 * 1024 * 1024


def image_dimensions(data):
    if not isinstance(data, bytes) or len(data) > MAX_IMAGE:
        raise ValueError('Comic pages are limited to 8 MiB.')
    if len(data) >= 33 and data[:8] == b'\x89PNG\r\n\x1a\n' and data[12:16] == b'IHDR':
        width, height = struct.unpack('>II', data[16:24])
    elif data.startswith(b'\xff\xd8'):
        offset, width, height = 2, 0, 0
        while offset + 4 <= len(data):
            if data[offset] != 255:
                raise ValueError('Invalid JPEG page.')
            while offset < len(data) and data[offset] == 255:
                offset += 1
            if offset >= len(data):
                break
            marker = data[offset]
            offset += 1
            if marker in (0xD9, 0xDA):
                break
            if marker == 0x01 or 0xD0 <= marker <= 0xD8:
                continue
            if offset + 2 > len(data):
                break
            length = int.from_bytes(data[offset:offset + 2], 'big')
            if length < 2 or offset + length > len(data):
                raise ValueError('Invalid JPEG segment.')
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                if length < 8:
                    raise ValueError('Invalid JPEG dimensions.')
                height, width = struct.unpack('>HH', data[offset + 3:offset + 7])
                break
            offset += length
    else:
        raise ValueError('Use PNG or JPEG comic pages.')
    if not 0 < width <= 8192 or not 0 < height <= 8192 or width * height > 16_000_000:
        raise ValueError('Page dimensions exceed the mobile 16-megapixel limit.')
    return width, height


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
                mime = 'image/png' if data.startswith(b'\x89PNG') else 'image/jpeg'
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
              f'<style>html{{color-scheme:{"light dark" if theme == "system" else theme}}}body{{font:{size}px system-ui;line-height:1.5;margin:{margin}px;overflow-wrap:anywhere}}'
              'img{max-width:100%;height:auto}pre{white-space:pre-wrap}table{max-width:100%}</style>'
              '</head><body>' + content + '</body></html>')
    if len(result.encode('utf-8')) > 2 * 1024 * 1024:
        raise ValueError('Rendered chapter exceeds the mobile 2 MiB limit.')
    return result
