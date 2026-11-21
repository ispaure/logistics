"""Internal PDF page links in normalized, rotated display coordinates."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from functools import cached_property
from io import BytesIO
import math


class PDFLinkIndex:
    """Keep one parsed PDF and lazily reuse its immutable destination maps."""

    def __init__(self, data):
        self.data = data

    @cached_property
    def reader(self):
        from pypdf import PdfReader
        return PdfReader(BytesIO(self.data))

    @cached_property
    def targets(self):
        return {page.indirect_reference: index for index, page in enumerate(self.reader.pages)}

    @cached_property
    def names(self):
        return self.reader.named_destinations

    def page_links(self, index):
        """Return plain rectangles/targets without executing PDF actions."""
        from .document import MAX_PDF, MAX_PAGES
        if not self.data or len(self.data) > MAX_PDF:
            return []
        reader = self.reader
        if reader.is_encrypted or not 0 <= index < len(reader.pages) <= MAX_PAGES:
            return []
        page = reader.pages[index]
        annotations = page.get('/Annots', [])
        if not annotations:
            return []
        box = page.cropbox
        left, bottom, width, height = map(float, (box.left, box.bottom, box.width, box.height))
        if not all(math.isfinite(v) for v in (left, bottom, width, height)) or min(width, height) <= 0:
            return []
        def point(x, y):
            x, y = (x-left)/width, 1-(y-bottom)/height
            return {0: (x, y), 90: (1-y, x), 180: (1-x, 1-y), 270: (y, 1-x)}[page.rotation % 360]
        links = []
        for annotation in annotations[:2000]:
            try:
                item = annotation.get_object()
                if item.get('/Subtype') != '/Link' or int(item.get('/F', 0)) & 35:
                    continue  # invisible, hidden or NoView
                action = item.get('/A', {}).get_object() if '/A' in item else {}
                if action and action.get('/S') != '/GoTo':
                    continue
                destination = action.get('/D') if action.get('/S') == '/GoTo' else item.get('/Dest')
                if destination is None:
                    continue
                destination = destination.get_object() if hasattr(destination, 'get_object') else destination
                if isinstance(destination, str):
                    target = reader.get_destination_page_number(self.names[destination])
                else:
                    if isinstance(destination, dict):
                        destination = destination['/D']
                    reference = destination[0]
                    target = self.targets.get(reference)
                if target is None or not 0 <= target < len(reader.pages):
                    continue
                x0, y0, x1, y1 = map(float, item['/Rect'])
                if not all(math.isfinite(v) for v in (x0, y0, x1, y1)):
                    continue
                a, b = point(x0, y0), point(x1, y1)
                rect = [max(0, min(a[0], b[0])), max(0, min(a[1], b[1])),
                        min(1, max(a[0], b[0])), min(1, max(a[1], b[1]))]
                if rect[0] < rect[2] and rect[1] < rect[3]:
                    links.append(dict(rect=rect, index=target))
            except (KeyError, TypeError, ValueError, AttributeError, IndexError):
                continue
        return links

    def safe_page_links(self, index):
        try:
            return self.page_links(index)
        except Exception:
            return []


def page_links(data, index):
    return PDFLinkIndex(data).page_links(index)


def safe_page_links(data, index):
    """Malformed optional annotations must not prevent reading or drawing."""
    return PDFLinkIndex(data).safe_page_links(index)
