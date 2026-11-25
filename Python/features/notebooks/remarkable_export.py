"""Portable RMDOC copies with vector backgrounds and unchanged native ink.

The desktop reMarkable importer retains template names but drops unregistered
custom .template files. Its supported self-contained background is an embedded
PDF. Working saves include the PDF and the information Logistics needs to
continue editing the templates. Recovery checkpoints can keep the lean notebook.
"""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json

from commonUtils.runtime.operations import check_cancelled

from .ink import WIDTH, HEIGHT
from .templates import (
    CATALOG, MOVE_WIDTH, MOVE_HEIGHT, TemplateLine, TemplatePDF, fixed_size, native_template, page_artwork, settings, template_name,
    template_requires_pdf,
)


# Native v6 scene units are 226 per inch; PDF uses 72 points per inch.
# Keep ink untouched and convert the background, including its page box.
PDF_SCALE = 72 / 226
WORKING_TEMPLATES = 'logistics-working-templates.json'
PDF_CONTENT_FIELDS = ('fileType', 'originalPageCount', 'redirectionPageMap')


class BackgroundConversionError(ValueError):
    """The artwork or ink cannot be represented by the portable background."""


def page_size(book, index):
    page = book.pages[index]
    paper = settings(book, page)
    move = paper['format'] == 'move' and fixed_size(book, page)
    width, height = (MOVE_WIDTH, MOVE_HEIGHT) if move else (WIDTH, HEIGHT)
    ink = book.page(index)
    if ink.warning:
        raise BackgroundConversionError('This page has unsupported native objects. Save preserves them; '
                                        'a template-to-PDF export cannot safely determine their bounds.')
    for stroke in ink.strokes:
        for x, y, pressure, point_width in stroke.points:
            radius = max(0, point_width) / 2 + 2
            if y < 0:
                raise BackgroundConversionError('Ink above the page cannot be exported with a fixed background. '
                                                'Save preserves the original notebook.')
            # A symmetric horizontal extension keeps native X=0 at page center.
            # Include hidden layers too: revealing one later must not clip ink.
            width = max(width, 2 * (abs(x - WIDTH / 2) + radius))
            height = max(height, y + radius)
    for image in ink.images:
        for x, y in image.corners:
            if y < 0:
                raise BackgroundConversionError('Images above the page cannot be exported with a fixed background.')
            width = max(width, 2 * abs(x - WIDTH / 2))
            height = max(height, y)
    return width, height


def needs_background_pdf(book):
    if book.content.get('fileType') == 'pdf':
        return False
    return any(template_requires_pdf(book, page, settings(book, page)) for page in book.pages)


def _pdf_number(value):
    return f'{value:.8f}'.rstrip('0').rstrip('.')


def pdf_template_line(line, *, dark=False):
    rgb = [value / 255 for value in bytes.fromhex(line.color[1:])]
    if dark:
        rgb = [1 - value for value in rgb]
    color = ' '.join(f'{value:.5f}' for value in rgb)
    x, y, end_x, end_y = map(_pdf_number, line.points)
    return f'{color} RG {_pdf_number(line.width)} w {x} {y} m {end_x} {end_y} l S'


def _pdf_template_label(label):
    try:
        text = label.text.encode('cp1252').decode('latin-1')
    except UnicodeEncodeError:
        raise BackgroundConversionError('This template includes text outside the supported PDF font encoding.') from None
    literal = text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
    x, y, size = map(_pdf_number, (label.x, label.y, label.size))
    # Reverse the text Y axis so glyphs remain upright in the top-down page coordinates.
    return f'BT /F1 {size} Tf 1 0 0 -1 {x} {y} Tm ({literal}) Tj ET'


def merge_pdf_template(target, artwork, *, scale, left, height, sources):
    """Place the template PDF in native scene coordinates, retaining text and vectors."""
    from pypdf import PdfReader, Transformation
    from pypdf.errors import PyPdfError

    try:
        source = sources.get(artwork.data)
        if source is None:
            reader = PdfReader(BytesIO(artwork.data))
            if reader.is_encrypted or len(reader.pages) != 1:
                raise ValueError('Expected one unencrypted page.')
            source = reader.pages[0]
            if source.rotation % 360 or source.get('/Annots'):
                raise ValueError('Expected an unrotated page without annotations.')
            sources[artwork.data] = source
        crop = source.cropbox
        source_width, source_height = float(crop.width), float(crop.height)
        if not (0 < source_width <= 5000 and 0 < source_height <= 5000):
            raise ValueError('Invalid template PDF page box.')
        bounds = artwork.bounds
        target.merge_transformed_page(source, Transformation()
            .translate(-float(crop.left), -float(crop.bottom))
            .scale(bounds['width'] * scale / source_width, bounds['height'] * scale / source_height)
            .translate((bounds['x'] - left) * scale, (height - bounds['y'] - bounds['height']) * scale))
    except (PyPdfError, ValueError, TypeError, KeyError, RecursionError) as error:
        raise BackgroundConversionError('This notebook includes a PDF template that cannot be embedded.') from error


def backgrounds_pdf(book, *, cancelled=lambda: False):
    """Render the same original primitives as the canvas, without rasterizing ink."""
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

    writer = PdfWriter()
    font = writer._add_object(DictionaryObject({
        NameObject('/Type'): NameObject('/Font'),
        NameObject('/Subtype'): NameObject('/Type1'),
        NameObject('/BaseFont'): NameObject('/Helvetica'),
        NameObject('/Encoding'): NameObject('/WinAnsiEncoding'),
    }))
    sources = {}
    for index, page in enumerate(book.pages):
        check_cancelled(cancelled)
        paper = settings(book, page)
        artwork = page_artwork(book, page, paper) if paper['visible'] else ()
        if artwork is None:
            raise BackgroundConversionError('This notebook includes template artwork unavailable to Logistics. '
                                            'Choose a supported background or hide it before exporting to reMarkable. '
                                            'Save retains the original notebook unchanged.')
        width, height = page_size(book, index)
        left = (WIDTH - width) / 2
        target = writer.add_blank_page(width=width * PDF_SCALE, height=height * PDF_SCALE)
        if isinstance(artwork, TemplatePDF):
            merge_pdf_template(target, artwork, scale=PDF_SCALE, left=left, height=height, sources=sources)
            continue
        target[NameObject('/Resources')] = DictionaryObject({
            NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
        commands = [f'q {PDF_SCALE:.12g} 0 0 {-PDF_SCALE:.12g} {-left * PDF_SCALE:.12g} {height * PDF_SCALE:.12g} cm',
                    '0.33333 0.33333 0.33333 rg']
        for item in artwork:
            commands.append(pdf_template_line(item) if isinstance(item, TemplateLine) else _pdf_template_label(item))
        commands.append('Q')
        stream = DecodedStreamObject()
        stream.set_data('\n'.join(commands).encode('latin-1'))
        target[NameObject('/Contents')] = writer._add_object(stream.flate_encode())
    writer.add_metadata({'/Title': book.name, '/Creator': 'Logistics', '/LogisticsNativeUnits': '226'})
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def export_rmdoc(book, *, cancelled=lambda: False):
    """Produce an importable copy while preserving the source's editable presets."""
    return _portable_archive(book, cancelled=cancelled)


def save_rmdoc(book, *, cancelled=lambda: False):
    """Bake portable paper on Save and retain the template references for Logistics."""
    try:
        return _portable_archive(book, editable=True, cancelled=cancelled)
    except BackgroundConversionError:
        # Imported notebooks can contain artwork or ink we can only preserve.
        check_cancelled(cancelled)
        return book.to_bytes()


def _portable_archive(book, *, editable=False, cancelled):
    check_cancelled(cancelled)
    if not needs_background_pdf(book):
        return book.to_bytes()
    from .notebook import Notebook, json_bytes

    pdf = backgrounds_pdf(book, cancelled=cancelled)
    check_cancelled(cancelled)
    copy = Notebook._from_members(book._archive_members(), max_bytes=book.max_bytes)
    if copy.id + '.pdf' in copy.members:
        raise BackgroundConversionError('The notebook already contains a PDF member. Save preserves it.')
    copy.members[copy.id + '.pdf'] = pdf
    if editable:
        working_key = f'{copy.id}/{WORKING_TEMPLATES}'
        if working_key in copy.members:
            raise BackgroundConversionError('The notebook already contains template recovery data. Save preserves it.')
        for page in copy.pages:
            name = template_name(page.template)
            path = page.template + '.template'
            if name.startswith('Logistics ') and name in CATALOG and path not in copy.members:
                copy.members[path] = native_template(name, settings(copy, page)['format'])
        pages = [[page.id, page.template] for page in copy.pages]
        copy.members[working_key] = json_bytes(dict(
            version=1, pdf_sha256=sha256(pdf).hexdigest(), pages=pages,
            templates_sha256=_template_files_digest(copy, pages),
            content={key: copy.content[key] for key in PDF_CONTENT_FIELDS if key in copy.content},
            redirects={page.id: page.record['redir'] for page in copy.pages if 'redir' in page.record}))
    copy.content.update(fileType='pdf', originalPageCount=len(copy.pages))
    for index, page in enumerate(copy.pages):
        page.record['redir'] = dict(value=index)
        page.template = 'Blank'
    copy.structure_dirty = True
    return copy.to_bytes()


def _template_files_digest(book, pages):
    paths = {template + '.template' for _, template in pages}
    paths.update(f'{book.id}/{page_id}.logistics-template.json' for page_id, _ in pages)
    hashes = []
    for path in sorted(paths):
        data = book.members.get(path)
        hashes.append((path, sha256(data).hexdigest() if data is not None else None))
    return sha256(json.dumps(hashes).encode()).hexdigest()


def restore_working_templates(book):
    """Open a portable working file in template mode when the PDF mapping still agrees."""
    from .notebook import json_bytes

    key = f'{book.id}/{WORKING_TEMPLATES}'
    raw = book.members.get(key)
    if raw is None or book.content.get('fileType') != 'pdf' or len(raw) > 16 * 1024 * 1024:
        return
    try:
        info = json.loads(raw)
        entries = info['pages']
        original = info['content']
        original_redirects = info['redirects']
        if (type(info['version']) is not int or info['version'] != 1 or not isinstance(entries, list)
                or len(entries) != len(book.pages) or not isinstance(original, dict)
                or original.keys() - set(PDF_CONTENT_FIELDS) or original.get('fileType', '') not in ('', 'notebook')
                or not isinstance(original_redirects, dict)):
            return
        templates = {}
        for index, entry in enumerate(entries):
            if not isinstance(entry, list) or len(entry) != 2:
                return
            page_id, template = entry
            if (not isinstance(page_id, str) or page_id in templates or not isinstance(template, str)
                    or len(template) > 512 or any(ord(c) < 32 or c in '\x85\u2028\u2029' for c in template)):
                return
            templates[page_id] = index, template
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return
    pdf_key = book.id + '.pdf'
    if any(page.id not in templates or page.template != 'Blank'
           or page.record.get('redir', {}).get('value', -1) != templates[page.id][0]
           for page in book.pages):
        return
    if (sha256(book.members[pdf_key]).hexdigest() != info.get('pdf_sha256')
            or _template_files_digest(book, entries) != info.get('templates_sha256')):
        return

    def restore_record(record, page_id):
        record.pop('redir', None)
        if page_id in original_redirects:
            record['redir'] = original_redirects[page_id]
        if 'template' in record:
            record['template']['value'] = templates[page_id][1]

    try:
        content = deepcopy(book.content)
        for record in content.get('cPages', {}).get('pages', []):
            if record['id'] in templates and record.get('deleted', {}).get('value') != 1:
                record.setdefault('template', {})
                restore_record(record, record['id'])
        for field in PDF_CONTENT_FIELDS:
            content.pop(field, None)
        content.update(original)
        content_bytes = json_bytes(content)
    except (TypeError, ValueError, RecursionError):
        return

    for page in book.pages:
        page.template = templates[page.id][1]
        restore_record(page.record, page.id)
    book.content = content
    book.members.pop(key)
    book.members.pop(pdf_key)
    book.members[book.id + '.content'] = content_bytes
    book.members[book.id + '.pagedata'] = ('\n'.join(page.template for page in book.pages) + '\n').encode()
