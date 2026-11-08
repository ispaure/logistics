"""Bounded scene data for the shared WebView brush renderer."""
from .ink import WIDTH, HEIGHT
from .templates import available, background, settings

BATCH = 16
POINTS = 8192
BATCH_POINTS = 16384
STROKES = 256
THUMBNAIL_EDGE = 288


def page_previews(book, start, *, pdf_bounds=None, pdf_artwork=None):
    if type(start) is not int or not 0 <= start < len(book.pages):
        raise ValueError('Invalid page overview range.')
    previews, remaining = [], BATCH_POINTS
    for index in range(start, min(start + BATCH, len(book.pages))):
        ink = book.page(index)
        page = book.pages[index]
        order = {key: i for i, key in enumerate(ink.order)}
        visible = {key: i for i, (key, _, shown) in enumerate(ink.layers) if shown}
        strokes = [s for s in ink.strokes if s.layer in visible and s.points]
        strokes.sort(key=lambda s: (visible[s.layer], order.get(s.id, len(order))))
        if len(strokes) > STROKES:
            strokes = [strokes[i * (len(strokes) - 1) // (STROKES - 1)] for i in range(STROKES)]
        total = sum(len(s.points) for s in strokes)
        if min(total, POINTS) > remaining:
            break
        remaining -= min(total, POINTS)
        minimum = sum(min(2, len(s.points)) for s in strokes)
        items = []
        bounds = pdf_bounds(index) if pdf_bounds else None
        left = min(0, bounds['x']) if bounds else 0
        height = max(HEIGHT, bounds['height']) if bounds else HEIGHT
        for stroke in strokes:
            points = stroke.points
            if total > POINTS and len(points) > 2:
                count = 2 + (len(points) - 2) * (POINTS - minimum) // (total - minimum)
                points = [points[i * (len(points) - 1) // (count - 1)] for i in range(count)]
            # The renderer uses stored widths, never pressure, for saved ink.
            items.append(dict(tool=stroke.tool, color=stroke.color, color_rgba=stroke.color_rgba,
                              points=[[round(x - left, 2), round(y, 2), 0, width] for x, y, _, width in points]))
        redirect = page.record.get('redir', {}).get('value', -1) if book.content.get('fileType') == 'pdf' else -1
        if redirect >= 0:
            artwork = pdf_artwork(redirect) if pdf_artwork else None
        else:
            paper = settings(book, page)
            artwork = background(page.template, paper['format']) if paper['visible'] and available(book, page) else None
        if bounds is not None:
            bounds = dict(bounds, x=bounds['x'] - left)
        previews.append(dict(index=index, width=WIDTH - 2 * left, height=height, items=items,
                             background=artwork, pdf_paper=bounds, warning=ink.warning, template=page.template))
    return previews
