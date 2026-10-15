"""Convert chapter XHTML into readable, inert Qt rich text."""
from xml.etree import ElementTree as ET
from .xhtml import chapter_document


def chapter_html(book, path, *, foreground, spacing):
    document = chapter_document(book.read(path))
    for parent in list(document.iter()):
        for child in list(parent):
            tag = child.tag.rsplit('}', 1)[-1] if isinstance(child.tag, str) else ''
            if tag in ('script', 'style', 'link', 'iframe', 'object', 'embed', 'audio', 'video') or not tag:
                parent.remove(child)
    for node in document.iter():
        if not isinstance(node.tag, str):
            continue
        node.tag = node.tag.rsplit('}', 1)[-1]
        if node.tag == 'image':  # Common SVG cover wrapper, rendered as an image.
            node.tag = 'img'
            node.set('src', node.get('{http://www.w3.org/1999/xlink}href', node.get('href', '')))
        if node.tag == 'svg':
            node.tag = 'div'
        for key in list(node.attrib):
            if key not in ('id', 'name', 'href', 'src', 'alt', 'colspan', 'rowspan', 'dir'):
                del node.attrib[key]
        if node.get('id'):
            anchor = ET.Element('a', {'name': node.get('id')})
            node.insert(0, anchor)
    body = next((node for node in document.iter() if node.tag == 'body'), document)
    return (f'<html><head><style>body {{ color: {foreground}; }} '
            f'p {{ line-height: {spacing}%; margin-bottom: 12px; }} '
            f'a {{ color: {foreground}; text-decoration: underline; }}</style></head>'
            + ET.tostring(body, encoding='unicode', method='html') + '</html>')
