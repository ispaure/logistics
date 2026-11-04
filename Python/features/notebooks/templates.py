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
FORM_TEMPLATES = frozenset({'Logistics Restaurant review', 'Logistics Meeting notes',
    'Logistics Daily planner', 'Logistics Checklist', 'Logistics Cornell notes', 'Logistics Weekly planner'})
TEMPLATE_NOTICE = ('Logistics draws its own previews and layouts. Compatible with reMarkable; '
                   'not affiliated with or endorsed by reMarkable.')


def description(name, *, artwork_available=True):
    name = template_name(name)
    if not artwork_available or name not in CATALOG:
        return 'Imported template artwork is preserved. Choose a Logistics template to replace only this page’s background.'
    if name in LINE_COUNTS and not name.startswith('Logistics '):
        return 'Original Logistics ruled preview. Native export uses the lined template already on your reMarkable.'
    if name == 'Blank':
        return 'Plain paper with no background markings.'
    return 'Original Logistics layout. Export Copy embeds a fixed PDF background beneath editable handwriting.'


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


def available(book, page):
    """Never substitute built-in artwork for a different imported asset."""
    name = template_name(page.template)
    if name not in CATALOG:
        return False
    raw = book.members.get(page.template + '.template')
    if raw is None:
        return True
    if not name.startswith('Logistics '):
        return False
    return same_artwork(raw, native_template(name, settings(book, page)['format']))


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


def select(book, index, name, paper_format, visible):
    if name not in CATALOG or paper_format not in FORMATS or type(visible) is not bool:
        raise ValueError('Choose a supported page template and paper format.')
    if book.content.get('fileType') == 'pdf':
        raise ValueError('PDF backgrounds are part of the source document; templates are available in notebooks.')
    page = book.pages[index]
    reference = name + (' Move' if paper_format == 'move' else ' Pro') if name.startswith('Logistics ') else name
    path = reference + '.template'
    artwork = None
    if name.startswith('Logistics '):
        artwork = native_template(name, paper_format)
        if path in book.members and not same_artwork(book.members[path], artwork):
            raise ValueError('This template name already has different artwork; the original was preserved.')
    page.template = reference
    saved = _stored_settings(book, page)
    saved.update(format=paper_format, visible=visible)
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


@lru_cache(maxsize=32)
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
