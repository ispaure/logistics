"""Bounded scene data for the shared WebView brush renderer."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from .images import image_data, image_source
from .ink import WIDTH, HEIGHT, notebook_ink_height
from .templates import TemplatePDF, artwork_background, page_artwork, settings

BATCH = 16
POINTS = 8192
BATCH_POINTS = 16384
BATCH_IMAGE_BYTES = 4 * 1024 * 1024
STROKES = 256
THUMBNAIL_EDGE = 288


def page_previews(book, start, *, pdf_bounds=None, pdf_artwork=None, count=BATCH, include_image_sources=True,
                  include_background=True):
    if type(start) is not int or not 0 <= start < len(book.pages):
        raise ValueError('Invalid page overview range.')
    previews, remaining, image_budget = [], BATCH_POINTS, BATCH_IMAGE_BYTES
    for index in range(start, min(start + min(count, BATCH), len(book.pages))):
        ink = book.page(index)
        page = book.pages[index]
        order = {key: i for i, key in enumerate(ink.order)}
        visible = {key: i for i, (key, _, shown) in enumerate(ink.layers) if shown}
        def scene_order(item):
            return visible[item.layer], order.get(item.id, len(order))

        strokes = sorted((s for s in ink.strokes if s.layer in visible and s.points), key=scene_order)
        if len(strokes) > STROKES:
            strokes = [strokes[i * (len(strokes) - 1) // (STROKES - 1)] for i in range(STROKES)]
        total = sum(len(s.points) for s in strokes)
        pictures = list(image_data(book, index, layers=visible)) if include_image_sources else [
            (picture, None) for picture in ink.images if picture.layer in visible]
        image_bytes = sum(len(data) for _, data in pictures if data is not None)
        if min(total, POINTS) > remaining or (previews and image_bytes > image_budget):
            break
        remaining -= min(total, POINTS)
        image_budget = max(0, image_budget - image_bytes)
        minimum = sum(min(2, len(s.points)) for s in strokes)
        items = []
        bounds = pdf_bounds(index) if pdf_bounds else None
        left = min(0, bounds['x']) if bounds else 0
        height = max(HEIGHT, bounds['height']) if bounds else HEIGHT
        if book.content.get('fileType') == 'notebook':
            height = notebook_ink_height(ink)
        for stroke in strokes:
            points = stroke.points
            if total > POINTS and len(points) > 2:
                sample_count = 2 + (len(points) - 2) * (POINTS - minimum) // (total - minimum)
                points = [points[i * (len(points) - 1) // (sample_count - 1)] for i in range(sample_count)]
            # Use the stored widths for geometry and pressure for graphite density.
            items.append((scene_order(stroke), dict(tool=stroke.tool, color=stroke.color, color_rgba=stroke.color_rgba,
                          points=[[round(x - left, 2), round(y, 2), pressure, width]
                                  for x, y, pressure, width in points])))
        for item in ink.text_highlights:
            if item.layer in visible:
                items.append((scene_order(item), item.payload(left)))
        for picture, data in pictures:
            item = dict(corners=[[x - left, y] for x, y in picture.corners])
            if data is None:
                item['id'] = picture.id
            else:
                item['src'] = image_source(data)
            items.append((scene_order(picture), item))
        items.sort(key=lambda item: item[0])
        redirect = page.record.get('redir', {}).get('value', -1) if book.content.get('fileType') == 'pdf' else -1
        template_bounds = None
        if not include_background:
            artwork = None
        elif redirect >= 0:
            artwork = pdf_artwork(redirect) if pdf_artwork else None
        else:
            paper = settings(book, page)
            template = page_artwork(book, page, paper) if paper['visible'] else None
            artwork = artwork_background(template)
            if isinstance(template, TemplatePDF):
                template_bounds = template.bounds
        if bounds is not None:
            bounds = dict(bounds, x=bounds['x'] - left)
        previews.append(dict(index=index, width=WIDTH - 2 * left, height=height,
                             items=[item for _, item in items],
                             background=artwork, pdf_paper=bounds, template_background_bounds=template_bounds,
                             warning=ink.warning, template=page.template))
    return previews
