"""Shared offline XHTML parsing for desktop and mobile book renderers."""
from html.entities import html5
import re
from .epub import parse_xml


def chapter_document(data):
    """Resolve standard named entities without fetching an external DTD."""
    def entity(match):
        name = match.group(1).decode('ascii')
        if name in ('amp', 'lt', 'gt', 'quot', 'apos') or name + ';' not in html5:
            return match.group(0)
        return ''.join(f'&#{ord(char)};' for char in html5[name + ';']).encode('ascii')
    return parse_xml(re.sub(rb'&([A-Za-z][A-Za-z0-9]+);', entity, data))
