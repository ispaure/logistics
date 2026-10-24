"""Inert offline EPUB HTML for mobile WebViews."""
import base64
from html import escape
from urllib.parse import quote
from features.books.xhtml import chapter_document
from features.books.epub import resolve_href
from features.images.validation import image_dimensions


def chapter_html(book, index, font_size=16, *, margin=16, theme='system', links=False, font_family='system', line_spacing=150, reading_width='800', justify=False):
    if not 0 <= index < len(book.spine):
        raise IndexError('Chapter does not exist.')
    size = int(font_size)
    if not 12 <= size <= 32:
        raise ValueError('Invalid reading font size.')
    if margin not in (8, 16, 24, 32) or theme not in ('system', 'light', 'dark', 'sepia', 'slate'):
        raise ValueError('Invalid reader appearance.')
    from .typography import css
    path = book.spine[index]
    source = book.read(path)
    if len(source) > 2 * 1024 * 1024:
        raise ValueError('Mobile EPUB chapters are limited to 2 MiB.')
    root = chapter_document(source)
    body = next((node for node in root.iter() if isinstance(node.tag, str)
                 and node.tag.rsplit('}', 1)[-1].lower() == 'body'), root)
    allowed = {'p', 'div', 'span', 'section', 'article', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
               'strong', 'b', 'em', 'i', 'u', 's', 'blockquote', 'pre', 'code', 'ul', 'ol', 'li',
               'table', 'thead', 'tbody', 'tr', 'th', 'td', 'sup', 'sub', 'br', 'hr'}
    blocked = {'head', 'script', 'style', 'iframe', 'object', 'embed', 'math',
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
        if tag in {'img', 'image'}:
            try:
                # EPUB cover pages commonly wrap a raster in SVG <image>.
                # Extract its bytes through the same bounded offline loader;
                # SVG markup, geometry and active attributes never reach WebKit.
                source = (node.get('src', '') if tag == 'img' else
                          node.get('href') or node.get('{http://www.w3.org/1999/xlink}href', ''))
                resource, _ = resolve_href(path, source)
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
        attributes = ''
        for key in ('id', 'name'):
            if node.get(key):
                attributes += f' {key}="{escape(node.get(key), quote=True)}"'
        if tag == 'a' and links and node.get('href'):
            try:
                from features.books.locations import link_destination
                link_destination(book, index, node.get('href'))
                attributes += ' href="reader-link:' + quote(node.get('href'), safe='') + '"'
            except ValueError:
                pass
        text = escape(node.text or '')
        for child in node:
            text += render(child, depth + 1) + escape(child.tail or '')
        if tag in {'br', 'hr'}:
            return '<' + tag + '>'
        if tag in allowed or tag == 'a':
            return '<' + tag + attributes + '>' + text + '</' + tag + '>'
        return '<span' + attributes + '>' + text + '</span>' if attributes else text
    content = render(body)
    language = (body.get('lang') or body.get('{http://www.w3.org/XML/1998/namespace}lang')
                or root.get('lang') or root.get('{http://www.w3.org/XML/1998/namespace}lang')
                or next(iter(book.values('language')), ''))
    result = ('<!doctype html><html lang="' + escape(language, quote=True) + '"><head><meta charset="utf-8">'
              '<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">'
              '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
              '<style>' + css(size, margin, theme, font_family=font_family, line_spacing=line_spacing, reading_width=reading_width, justify=justify) +
              'img{max-width:100%;height:auto}pre{white-space:pre-wrap}table{max-width:100%}</style>'
              '</head><body>' + content + '</body></html>')
    if len(result.encode('utf-8')) > 2 * 1024 * 1024:
        raise ValueError('Rendered chapter exceeds the mobile 2 MiB limit.')
    return result


def chapter_text(book, index):
    """Inert text fallback for provider readers, without a native WebView."""
    from html.parser import HTMLParser
    class Text(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts, self.hidden = [], 0
        def handle_starttag(self, tag, attrs):
            if tag in {'head', 'style', 'script'}:
                self.hidden += 1
            if tag in {'p', 'div', 'br', 'h1', 'h2', 'h3', 'li', 'tr'} and not self.hidden:
                self.parts.append('\n')
        def handle_endtag(self, tag):
            if tag in {'head', 'style', 'script'}:
                self.hidden = max(0, self.hidden - 1)
        def handle_data(self, value):
            if not self.hidden:
                self.parts.append(value)
    parser = Text()
    parser.feed(chapter_html(book, index))
    return ''.join(parser.parts)


def indexed_chapter(book, index, font_size=16, **options):
    """Prepare inert HTML and its UTF-16 text index together in a worker."""
    from features.books.locations import ChapterText
    content = chapter_html(book, index, font_size, **options)
    return content, ChapterText(content)
