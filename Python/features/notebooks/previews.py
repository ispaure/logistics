"""Bounded ink thumbnails requested by desktop and mobile page overviews."""
import base64
import math

from .brushes import PALETTE
from .ink import WIDTH, HEIGHT

BATCH = 16
POINTS = 2048
STROKES = 256


def page_previews(book, start):
    if type(start) is not int or not 0 <= start < len(book.pages):
        raise ValueError('Invalid page overview range.')
    previews = []
    for index in range(start, min(start + BATCH, len(book.pages))):
        ink = book.page(index)
        visible = {key for key, _, shown in ink.layers if shown}
        strokes = [stroke for stroke in ink.strokes if stroke.layer in visible and stroke.points]
        strokes = strokes[::max(1, math.ceil(len(strokes) / STROKES))]
        budget = max(2, POINTS // max(1, len(strokes)))
        paths = []
        for stroke in strokes:
            points = stroke.points[::max(1, math.ceil(len(stroke.points) / (budget - 1)))]
            if points[-1] is not stroke.points[-1]:
                points = [*points, stroke.points[-1]]
            color = PALETTE.get(stroke.color, '#000000')
            opacity = 1
            if stroke.color_rgba:
                r, g, b, a = stroke.color_rgba
                color, opacity = f'#{r:02x}{g:02x}{b:02x}', a / 255
            geometry = 'M' + ' L'.join(f'{p[0]:.1f},{p[1]:.1f}' for p in points)
            if len(points) == 1:
                geometry += ' l0,.1'
            width = max(2, sum(p[3] for p in points) / len(points))
            paths.append(f'<path d="{geometry}" stroke="{color}" stroke-width="{width:.1f}" opacity="{opacity:.2f}"/>')
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}">'
               '<rect width="100%" height="100%" fill="white"/>'
               '<g fill="none" stroke-linecap="round" stroke-linejoin="round">' + ''.join(paths) + '</g></svg>')
        previews.append(dict(index=index, image='data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode(),
                             warning=ink.warning, template=book.pages[index].template))
    return previews
