"""Original notebook backgrounds and stable Pro/Move viewing geometry.

Ink always uses the existing 1404 x 1872 scene. A Move view is a crop, never
another ink coordinate system. Native stock names remain native references.
"""
import base64
from functools import lru_cache
from html import escape
import json

from .ink import WIDTH, HEIGHT

# Physical screen aspects, expressed in the existing native scene coordinate space.
MOVE_WIDTH, MOVE_HEIGHT = 821, 1460
CATALOG = {
    'Blank': 'Blank',
    'P Lines small': 'Lined — small',
    'P Lines medium': 'Lined — medium (reMarkable, 25 lines)',
    'Logistics Lined medium': 'Lined — medium (31 lines)',
    'P Lines large': 'Lined — large',
    'Logistics Grid': 'Grid',
    'Logistics Dots': 'Dots',
    'Logistics Restaurant review': 'Restaurant review',
    'Logistics Meeting notes': 'Meeting notes',
    'Logistics Daily planner': 'Daily planner',
}
# User-confirmed Paper Pro counts: large 21, medium 25, small 41.
# Keep native medium faithful; offer the requested more distinct medium separately.
LINE_COUNTS = {'P Lines small': 41, 'P Lines medium': 25, 'P Lines large': 21, 'Logistics Lined medium': 31}
FORMATS = {'pro': 'Paper Pro', 'move': 'Paper Pro Move'}


def template_name(reference):
    for name in CATALOG:
        if reference == name or reference in (name + ' Pro', name + ' Move'):
            return name
    return reference


def settings(book, page):
    raw = book.members.get(f'{book.id}/{page.id}.logistics-template.json', b'{}')
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            return dict(format='pro', visible=True)
        return dict(format=value.get('format') if value.get('format') in FORMATS else 'pro',
                    visible=value.get('visible') is not False)
    except (ValueError, UnicodeError):
        return dict(format='pro', visible=True)


def select(book, index, name, paper_format, visible):
    if name not in CATALOG or paper_format not in FORMATS or type(visible) is not bool:
        raise ValueError('Choose a supported page template and paper format.')
    if book.content.get('fileType') == 'pdf':
        raise ValueError('PDF backgrounds are part of the source document; templates are available in notebooks.')
    page = book.pages[index]
    page.template = name + (' Move' if paper_format == 'move' else ' Pro') if name.startswith('Logistics ') else name
    book.members[f'{book.id}/{page.id}.logistics-template.json'] = json.dumps(
        dict(format=paper_format, visible=visible)).encode()
    book.structure_dirty = True
    if name.startswith('Logistics '):
        artwork = native_template(name, paper_format)
        path = page.template + '.template'
        if path in book.members and book.members[path] != artwork:
            raise ValueError('This template name already has different artwork; the original was preserved.')
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
        if name == 'Logistics Restaurant review':
            fields = [('Restaurant / location', 125), ('Date / occasion / company', 255),
                      ('Dishes and drinks', 385), ('Food / service / atmosphere / value', 675),
                      ('Highlights and what to try next', 875), ('Overall rating / would return?', height - 200)]
        elif name == 'Logistics Meeting notes':
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


@lru_cache(maxsize=32)
def svg(name, paper_format='pro'):
    name = template_name(name)
    if name not in CATALOG or name == 'Blank':
        return ''
    paths, texts = geometry(name, paper_format)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}">'
            '<g fill="none" stroke="#a6aaa8" stroke-width="1.5">'
            + ''.join(f'<path d="{path}"/>' for path in paths) + '</g>'
            + ''.join(f'<text x="{x:g}" y="{y:g}" font-size="{size}" '
                      f'font-family="sans-serif" fill="#555">{escape(text)}</text>'
                      for text, x, y, size in texts) + '</svg>')


@lru_cache(maxsize=32)
def background(name, paper_format='pro'):
    artwork = svg(name, paper_format)
    return 'data:image/svg+xml;base64,' + base64.b64encode(artwork.encode()).decode() if artwork else None


def native_template(name, paper_format):
    """Embed original native vector artwork; no PDF conversion or ink flattening."""
    paths, texts = geometry(name, paper_format)
    items = [dict(type='path', data=[float(v) if v not in ('M', 'L') else v for v in path.split()],
                  strokeColor='#a6aaa8', strokeWidth=1.5) for path in paths]
    items += [dict(type='text', text=text, position=[x, y], fontSize=size) for text, x, y, size in texts]
    for i, item in enumerate(items):
        item['id'] = 'item' + str(i)
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
