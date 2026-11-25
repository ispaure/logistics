"""Original notebook backgrounds and stable Pro/Move viewing geometry.

Ink always uses the existing 1404 x 1872 scene. A Move view is a crop, never
another ink coordinate system. Native stock names remain native references.
"""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import base64
from dataclasses import dataclass, field
from functools import cached_property, lru_cache
from html import escape
import json
import re

from .assets import asset_bytes
from .ink import WIDTH, HEIGHT

# Physical screen aspects, expressed in the existing native scene coordinate space.
MOVE_WIDTH, MOVE_HEIGHT = 821, 1460
CATALOG = {
    'Blank': 'Blank',
    'P Lines small': 'Lined — small (41 lines; reMarkable compatible)',
    'P Lines medium': 'Lined — medium (25 lines; reMarkable compatible)',
    'Logistics Lined medium': 'Lined — medium (31 lines)',
    'P Lines large': 'Lined — large (21 lines; reMarkable compatible)',
    'Logistics Grid': 'Grid',
    'Logistics Dots': 'Dots',
    'Logistics Restaurant review': 'Restaurant review',
    'Logistics Meeting notes': 'Meeting notes',
    'Logistics Daily planner': 'Daily planner',
    'Logistics Checklist': 'Checklist',
    'Logistics Cornell notes': 'Cornell notes',
    'Logistics Weekly planner': 'Weekly planner',
}
# User-confirmed Paper Pro counts: large 21, medium 25, small 41.
# Keep native medium faithful; offer the requested more distinct medium separately.
LINE_COUNTS = {'P Lines small': 41, 'P Lines medium': 25, 'P Lines large': 21, 'Logistics Lined medium': 31}
FORMATS = {'pro': 'Paper Pro size', 'move': 'Paper Pro Move size'}
DINING_JOURNAL = 'Logistics Restaurant review'
DINING_ASSETS = {'pro': 'Dining_Journal_Paper_Pro_v6.pdf', 'move': 'Dining_Journal_Paper_Pro_Move_v6.pdf'}
FORM_TEMPLATES = frozenset({'Logistics Restaurant review', 'Logistics Meeting notes',
    'Logistics Daily planner', 'Logistics Checklist', 'Logistics Cornell notes', 'Logistics Weekly planner'})
TEMPLATE_NOTICE = ('Logistics draws its own previews and layouts. Compatible with reMarkable; '
                   'not affiliated with or endorsed by reMarkable.')


def description(name, *, artwork_available=True):
    name = template_name(name)
    if not artwork_available:
        return 'Imported template artwork is preserved. Choose a Logistics template to replace only this page’s background.'
    if name not in CATALOG:
        return 'Embedded layout. Save includes a fixed PDF background for reMarkable.'
    if name in LINE_COUNTS and not name.startswith('Logistics '):
        return 'Original Logistics ruled preview. Native export uses the lined template already on your reMarkable.'
    if name == 'Blank':
        return 'Plain paper with no background markings.'
    return 'Original Logistics layout. Save includes a fixed PDF background for reMarkable.'


def template_name(reference):
    for name in CATALOG:
        if reference == name or (name.startswith('Logistics ') and reference in (name + ' Pro', name + ' Move')):
            return name
    return reference


def _stored_settings(book, page):
    raw = book.members.get(f'{book.id}/{page.id}.logistics-template.json', b'{}')
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (ValueError, UnicodeError, RecursionError):
        return {}


def settings(book, page):
    reference_format = None
    if page.template.startswith('Logistics '):
        reference_format = 'move' if page.template.endswith(' Move') else 'pro' if page.template.endswith(' Pro') else None
    value = _stored_settings(book, page)
    paper_format = reference_format or value.get('format')
    if not isinstance(paper_format, str) or paper_format not in FORMATS:
        paper_format = 'pro'
    return dict(format=paper_format, visible=value.get('visible') is not False)


def fixed_size(book, page):
    return (template_name(page.template) in FORM_TEMPLATES
            or _stored_settings(book, page).get('fixed_size') is True)


def template_requires_pdf(book, page, paper):
    return (page.template + '.template' in book.members or page.template.startswith('Logistics ')
            or (page.template != 'Blank' and not paper['visible']))


def page_artwork(book, page, paper):
    """Use the saved artwork when present, including older versions of a preset."""
    raw = book.members.get(page.template + '.template')
    name = template_name(page.template)
    if raw is not None:
        if name == DINING_JOURNAL and raw == native_template(name, paper['format']):
            return catalog_artwork(name, paper['format'])
        cache = book._pdf_template_cache
        cached = cache.get(page.template)
        artwork = cached[1] if cached and cached[0] is raw else embedded_artwork(raw)
        if isinstance(artwork, TemplatePDF):
            if artwork.paper_format != paper['format']:
                return None
            if not cached or cached[0] is not raw:
                if len(cache) == 4:
                    cache.pop(next(iter(cache)))
                cache[page.template] = (raw, artwork)
        return artwork
    if name in CATALOG:
        return catalog_artwork(name, paper['format'])
    return None


def same_artwork(first, second):
    # Imported assets may belong to a private notebook. Do not retain their
    # bytes in a process-wide cache after the document session is retired.
    if first == second:
        return True
    try:
        return json.loads(first) == json.loads(second)
    except (ValueError, UnicodeError, RecursionError):
        return False


def inherit(book, source, target):
    """A new page shares its reference and copies opaque display settings."""
    target.template = source.template
    raw = book.members.get(f'{book.id}/{source.id}.logistics-template.json')
    if raw is not None:
        book.members[f'{book.id}/{target.id}.logistics-template.json'] = raw


def _preset_reference(name, paper_format):
    if not name.startswith('Logistics '):
        return name
    return name + (' Move' if paper_format == 'move' else ' Pro')


def template_updates(book, name):
    """Find saved Logistics preset variants whose embedded artwork has changed."""
    if book.content.get('fileType') == 'pdf' or not name.startswith('Logistics ') or name not in CATALOG:
        return {}
    updates = {}
    for paper_format in FORMATS:
        reference = _preset_reference(name, paper_format)
        raw = book.members.get(reference + '.template')
        if raw is None:
            continue
        latest = native_template(name, paper_format)
        if raw != latest:
            artwork = embedded_artwork(raw, logistics_only=True)
            if artwork is not None and artwork != catalog_artwork(name, paper_format):
                updates[reference] = latest
    return updates


def update_template(book, page):
    updates = template_updates(book, template_name(page.template))
    if not updates:
        raise ValueError('No layout update is available for this template.')
    book.members.update({reference + '.template': data for reference, data in updates.items()})
    book.structure_dirty = True


def select(book, index, name, paper_format, visible, *, lock_size=False):
    if name not in CATALOG or paper_format not in FORMATS or type(visible) is not bool:
        raise ValueError('Choose a supported page template and paper format.')
    if book.content.get('fileType') == 'pdf':
        raise ValueError('PDF backgrounds are part of the source document; templates are available in notebooks.')
    page = book.pages[index]
    reference = _preset_reference(name, paper_format)
    path = reference + '.template'
    artwork = None
    if name.startswith('Logistics '):
        if path not in book.members:
            artwork = native_template(name, paper_format)
        elif embedded_artwork(book.members[path]) is None:
            raise ValueError('This template name already has different artwork; the original was preserved.')
    page.template = reference
    saved = _stored_settings(book, page)
    saved.update(format=paper_format, visible=visible)
    if lock_size:
        saved['fixed_size'] = True
    book.members[f'{book.id}/{page.id}.logistics-template.json'] = json.dumps(saved).encode()
    book.structure_dirty = True
    if artwork is not None and path not in book.members:
        book.members[path] = artwork


def geometry(name, paper_format):
    """Original vector primitives, shared by preview and embedded native artwork."""
    paths, texts = [], []
    def line(x, y, x2, y2):
        paths.append(f'M {x:g} {y:g} L {x2:g} {y2:g}')
    def label(text, x, y, size=22):
        texts.append((text, x, y, size))
    if name in LINE_COUNTS:
        count = LINE_COUNTS[name]
        for i in range(count):
            y = 72 + i * (HEIGHT - 144) / (count - 1)
            line(0, y, WIDTH, y)
    elif name in ('Logistics Grid', 'Logistics Dots'):
        for y in range(48, HEIGHT, 48):
            if name == 'Logistics Grid':
                line(0, y, WIDTH, y)
            else:
                for x in range(24, WIDTH, 48):
                    line(x, y, x + 1.5, y)
        if name == 'Logistics Grid':
            for x in range(24, WIDTH, 48):
                line(x, 0, x, HEIGHT)
    elif name.startswith('Logistics '):
        width, height = (MOVE_WIDTH, MOVE_HEIGHT) if paper_format == 'move' else (WIDTH, HEIGHT)
        left = (WIDTH - width) / 2 + 40
        right = (WIDTH + width) / 2 - 40
        label(name.removeprefix('Logistics '), left, 64, 32)
        if name == 'Logistics Checklist':
            for y in range(132, height - 40, 70):
                line(left, y - 20, left + 22, y - 20)
                line(left + 22, y - 20, left + 22, y + 2)
                line(left + 22, y + 2, left, y + 2)
                line(left, y + 2, left, y - 20)
                line(left + 42, y + 2, right, y + 2)
            return paths, texts
        if name == 'Logistics Cornell notes':
            divider, summary = left + (right - left) * .28, height - 300
            label('Cues', left, 115)
            label('Notes', divider + 20, 115)
            line(divider, 132, divider, summary)
            line(left, summary, right, summary)
            label('Summary', left, summary + 36)
            for y in range(165, int(summary), 54):
                line(divider + 20, y, right, y)
            for y in range(int(summary + 80), height - 35, 54):
                line(left, y, right, y)
            return paths, texts
        if name == 'Logistics Weekly planner':
            step = (height - 180) / 7
            for index, day in enumerate(('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')):
                y = 132 + index * step
                label(day, left, y)
                line(left, y + step - 28, right, y + step - 28)
            return paths, texts
        if name == 'Logistics Meeting notes':
            fields = [('Topic / date', 125), ('People', 255), ('Discussion', 385),
                      ('Decisions', height - 540), ('Actions / owner / due', height - 300)]
        else:
            fields = [('Date / focus', 125), ('Top priorities', 255), ('Schedule / plans', 545),
                      ('Notes / reflection', height - 430)]
        for n, (title, y) in enumerate(fields):
            label(title, left, y)
            stop = fields[n + 1][1] - 52 if n + 1 < len(fields) else height - 40
            for baseline in range(int(y + 48), int(stop) + 1, 54):
                line(left, baseline, right, baseline)
    return paths, texts


def rule_style(name):
    if name in LINE_COUNTS or name == 'Logistics Grid':
        return '#c7ccd0', .9
    return '#a6aaa8', 1.5


@dataclass(frozen=True)
class TemplateLine:
    points: tuple
    color: str
    width: float


@dataclass(frozen=True)
class TemplateLabel:
    text: str
    x: float
    y: float
    size: float


@dataclass(frozen=True)
class TemplatePDF:
    data: bytes
    paper_format: str
    preview_asset: str | None = field(default=None, compare=False)

    @property
    def bounds(self):
        return view_bounds([], self.paper_format == 'move')

    @cached_property
    def preview(self):
        if self.preview_asset is not None:
            return asset_bytes(self.preview_asset)
        from features.pdf.document import PDFDocument

        return PDFDocument.render_page(self.data, 0, edge=HEIGHT)

    @cached_property
    def preview_url(self):
        return 'data:image/png;base64,' + base64.b64encode(self.preview).decode('ascii')


@lru_cache(maxsize=32)
def catalog_artwork(name, paper_format):
    if name == DINING_JOURNAL:
        asset_name = DINING_ASSETS[paper_format]
        return TemplatePDF(asset_bytes(asset_name), paper_format, asset_name.removesuffix('.pdf') + '_preview.png')
    paths, texts = geometry(name, paper_format)
    color, weight = rule_style(name)
    lines = []
    for path in paths:
        _, x, y, _, end_x, end_y = path.split()
        lines.append(TemplateLine(tuple(float(value) for value in (x, y, end_x, end_y)), color, weight))
    return tuple(lines) + tuple(TemplateLabel(*text) for text in texts)


def _coordinate(value):
    return type(value) in (int, float) and -100_000 <= value <= 100_000


def embedded_artwork(raw, *, logistics_only=False):
    """Read the bounded line and label format used by Logistics saves."""
    # The largest catalog drawing is under 2,000 line segments. Bound imported
    # artwork before decoding it or sending the rendered SVG to the WebView.
    if len(raw) > 512 * 1024:
        return None
    try:
        asset = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        return None
    if (not isinstance(asset, dict) or type(asset.get('formatVersion')) is not int
            or (logistics_only and asset.get('author') != 'Logistics')):
        return None
    if asset['formatVersion'] == 2:
        paper_format, encoded_pdf = asset.get('paperFormat'), asset.get('pdf')
        if (asset.get('author') != 'Logistics' or not isinstance(paper_format, str)
                or paper_format not in FORMATS or not isinstance(encoded_pdf, str)):
            return None
        try:
            data = base64.b64decode(encoded_pdf, validate=True)
        except ValueError:
            return None
        return TemplatePDF(data, paper_format) if data.startswith(b'%PDF-') else None
    if (asset['formatVersion'] != 1 or asset.get('orientation') != 'portrait' or asset.get('constants') != []
            or not isinstance(asset.get('items'), list) or len(asset['items']) > 4096):
        return None
    artwork = []
    for item in asset['items']:
        if not isinstance(item, dict):
            return None
        if item.get('type') == 'path':
            data, color, width = item.get('data'), item.get('strokeColor'), item.get('strokeWidth')
            if (item.keys() - {'id', 'type', 'data', 'strokeColor', 'strokeWidth'}
                    or not isinstance(data, list) or len(data) != 6 or data[0] != 'M' or data[3] != 'L'
                    or not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color)
                    or not _coordinate(width) or width <= 0):
                return None
            points = data[1:3] + data[4:6]
            if not all(map(_coordinate, points)):
                return None
            artwork.append(TemplateLine(tuple(points), color, width))
        elif item.get('type') == 'text':
            text, position, size = item.get('text'), item.get('position'), item.get('fontSize')
            if (item.keys() - {'id', 'type', 'text', 'position', 'fontSize'}
                    or not isinstance(text, str) or len(text) > 1024 or not text.isprintable()
                    or not isinstance(position, list) or len(position) != 2 or not all(map(_coordinate, position))
                    or not _coordinate(size) or size <= 0):
                return None
            artwork.append(TemplateLabel(text, *position, size))
        else:
            return None
    return tuple(artwork)


def artwork_svg(artwork):
    if not artwork or isinstance(artwork, TemplatePDF):
        return ''
    elements = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">']
    for item in artwork:
        if isinstance(item, TemplateLine):
            x, y, end_x, end_y = item.points
            elements.append(f'<path d="M {x:g} {y:g} L {end_x:g} {end_y:g}" fill="none" '
                            f'stroke="{item.color}" stroke-width="{item.width:g}"/>')
        else:
            elements.append(f'<text x="{item.x:g}" y="{item.y:g}" font-size="{item.size:g}" '
                            f'font-family="sans-serif" fill="#555">{escape(item.text)}</text>')
    return ''.join(elements) + '</svg>'


@lru_cache(maxsize=32)
def svg(name, paper_format='pro'):
    name = template_name(name)
    if name not in CATALOG or name == 'Blank':
        return ''
    return artwork_svg(catalog_artwork(name, paper_format))


def _image_source(svg):
    return 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode() if svg else None


def artwork_background(artwork):
    if isinstance(artwork, TemplatePDF):
        try:
            return artwork.preview_url
        except (OSError, ValueError):
            return None
    return _image_source(artwork_svg(artwork))


@lru_cache(maxsize=32)
def background(name, paper_format='pro'):
    name = template_name(name)
    return artwork_background(catalog_artwork(name, paper_format)) if name in CATALOG else None


@lru_cache(maxsize=32)
def preview_svg(name, paper_format):
    """Clip the original artwork to the selected paper, without scaling ink coordinates."""
    bounds = view_bounds([], paper_format == 'move')
    x, y, width, height = (bounds[key] for key in ('x', 'y', 'width', 'height'))
    artwork = svg(name, paper_format).partition('>')[2].removesuffix('</svg>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="{x:g} {y:g} {width} {height}">'
            f'<rect x="{x:g}" width="{width}" height="{height}" fill="white"/>{artwork}</svg>')


@lru_cache(maxsize=32)
def native_template(name, paper_format):
    """Embed the preset's original artwork separately from ink."""
    artwork = catalog_artwork(name, paper_format)
    if isinstance(artwork, TemplatePDF):
        return json.dumps(dict(name=CATALOG[name], author='Logistics', templateVersion='6.0.0',
                               formatVersion=2, paperFormat=paper_format,
                               pdf=base64.b64encode(artwork.data).decode('ascii'))).encode()
    items = []
    for index, item in enumerate(artwork):
        if isinstance(item, TemplateLine):
            x, y, end_x, end_y = item.points
            entry = dict(type='path', data=['M', x, y, 'L', end_x, end_y], strokeColor=item.color, strokeWidth=item.width)
        else:
            entry = dict(type='text', text=item.text, position=[item.x, item.y], fontSize=item.size)
        entry['id'] = 'item' + str(index)
        items.append(entry)
    return json.dumps(dict(name=CATALOG[name], author='Logistics', templateVersion='1.0.0',
                           formatVersion=1, orientation='portrait', categories=['Methods'],
                           constants=[], items=items)).encode()


def view_bounds(strokes, move=False):
    if not move:
        return dict(x=0, y=0, width=WIDTH, height=HEIGHT)
    left, right, bottom = (WIDTH - MOVE_WIDTH) / 2, (WIDTH + MOVE_WIDTH) / 2, MOVE_HEIGHT
    # Include all ink, even hidden layers, so changing layer visibility cannot
    # strand writing outside the available paper. Include actual stroke radii.
    for stroke in strokes:
        for x, y, _, width in stroke.points:
            radius = max(0, width) / 2 + 2
            left, right = min(left, x - radius), max(right, x + radius)
            bottom = max(bottom, y + radius)
    left, right, bottom = max(0, left), min(WIDTH, right), min(HEIGHT, bottom)
    return dict(x=left, y=0, width=right - left, height=bottom)
