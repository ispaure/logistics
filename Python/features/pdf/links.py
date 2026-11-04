"""Internal PDF page links in normalized, rotated display coordinates."""
from io import BytesIO
import math


def page_links(data, index):
    """Return plain rectangles/targets; never execute PDF actions or open files."""
    from pypdf import PdfReader
    from .document import MAX_PDF, MAX_PAGES
    if not data or len(data) > MAX_PDF:
        return []
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted or not 0 <= index < len(reader.pages) <= MAX_PAGES:
        return []
    page = reader.pages[index]
    box = page.cropbox
    left, bottom, width, height = map(float, (box.left, box.bottom, box.width, box.height))
    if not all(math.isfinite(v) for v in (left, bottom, width, height)) or min(width, height) <= 0:
        return []
    def point(x, y):
        x, y = (x-left)/width, 1-(y-bottom)/height
        return {0: (x, y), 90: (1-y, x), 180: (1-x, 1-y), 270: (y, 1-x)}[page.rotation % 360]
    links = []
    names = None
    targets = {p.indirect_reference: i for i, p in enumerate(reader.pages)}
    for annotation in page.get('/Annots', [])[:2000]:
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
                if names is None:
                    names = reader.named_destinations
                target = reader.get_destination_page_number(names[destination])
            else:
                if isinstance(destination, dict):
                    destination = destination['/D']
                reference = destination[0]
                target = targets.get(reference)
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


def safe_page_links(data, index):
    """Malformed optional annotations must not prevent reading or drawing."""
    try:
        return page_links(data, index)
    except Exception:
        return []
