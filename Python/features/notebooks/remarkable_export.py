"""Portable RMDOC copies with vector backgrounds and unchanged native ink.

The desktop reMarkable importer retains template names but drops unregistered
custom .template files. Its supported self-contained background is an embedded
PDF. Only Export Copy uses this conversion; saves and recovery retain templates.
"""
from io import BytesIO

from commonUtils.runtime.operations import check_cancelled

from .ink import WIDTH, HEIGHT
from .templates import MOVE_WIDTH, MOVE_HEIGHT, available, geometry, settings, template_name


# Native v6 scene units are 226 per inch; PDF uses 72 points per inch.
# Keep ink untouched and convert the background, including its page box.
PDF_SCALE = 72 / 226
FORMS = {'Logistics Restaurant review', 'Logistics Meeting notes', 'Logistics Daily planner'}


def page_size(book, index):
    page = book.pages[index]
    paper = settings(book, page)
    move = paper['format'] == 'move' and template_name(page.template) in FORMS
    width, height = (MOVE_WIDTH, MOVE_HEIGHT) if move else (WIDTH, HEIGHT)
    ink = book.page(index)
    if ink.warning:
        raise ValueError('This page has unsupported native objects. Save preserves them; '
                         'a template-to-PDF export cannot safely determine their bounds.')
    for stroke in ink.strokes:
        for x, y, pressure, point_width in stroke.points:
            radius = max(0, point_width) / 2 + 2
            if y < 0:
                raise ValueError('Ink above the page cannot be exported with a fixed background. '
                                 'Save preserves the original notebook.')
            # A symmetric horizontal extension keeps native X=0 at page center.
            # Include hidden layers too: revealing one later must not clip ink.
            width = max(width, 2 * (abs(x - WIDTH / 2) + radius))
            height = max(height, y + radius)
    return width, height


def needs_background_pdf(book):
    if book.content.get('fileType') == 'pdf':
        return False
    return any(template_name(page.template).startswith('Logistics ')
               or (page.template != 'Blank' and not settings(book, page)['visible'])
               for page in book.pages)


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
    for index, page in enumerate(book.pages):
        check_cancelled(cancelled)
        paper = settings(book, page)
        paths, texts = [], []
        if paper['visible'] and page.template != 'Blank':
            if not available(book, page):
                raise ValueError('This notebook includes template artwork unavailable to Logistics. '
                                 'Choose a supported background or hide it before exporting to reMarkable. '
                                 'Save retains the original notebook unchanged.')
            paths, texts = geometry(template_name(page.template), paper['format'])
        width, height = page_size(book, index)
        left = (WIDTH - width) / 2
        target = writer.add_blank_page(width=width * PDF_SCALE, height=height * PDF_SCALE)
        target[NameObject('/Resources')] = DictionaryObject({
            NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
        commands = [f'q {PDF_SCALE:.12g} 0 0 {-PDF_SCALE:.12g} {-left * PDF_SCALE:.12g} {height * PDF_SCALE:.12g} cm', '0.65098 0.66667 0.65882 RG 1.5 w']
        for path in paths:
            _, x, y, _, x2, y2 = path.split()
            commands.append(f'{x} {y} m {x2} {y2} l S')
        commands.append('0.33333 0.33333 0.33333 rg')
        for text, x, y, size in texts:
            literal = text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
            # The page CTM uses top-down canvas coordinates. Reverse the text
            # matrix's Y axis again to keep glyphs upright at the same baseline.
            commands.append(f'BT /F1 {size} Tf 1 0 0 -1 {x:g} {y:g} Tm ({literal}) Tj ET')
        commands.append('Q')
        stream = DecodedStreamObject()
        stream.set_data('\n'.join(commands).encode('ascii'))
        target[NameObject('/Contents')] = writer._add_object(stream.flate_encode())
    writer.add_metadata({'/Title': book.name, '/Creator': 'Logistics', '/LogisticsNativeUnits': '226'})
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def export_rmdoc(book, *, cancelled=lambda: False):
    """Produce an importable copy while preserving the source's editable presets."""
    check_cancelled(cancelled)
    if not needs_background_pdf(book):
        return book.to_bytes()
    from .notebook import Notebook

    pdf = backgrounds_pdf(book, cancelled=cancelled)
    check_cancelled(cancelled)
    copy = Notebook.read(book.to_bytes())
    copy.members[copy.id + '.pdf'] = pdf
    copy.content.update(fileType='pdf', originalPageCount=len(copy.pages))
    for index, page in enumerate(copy.pages):
        page.record['redir'] = dict(value=index)
        page.template = 'Blank'
    copy.structure_dirty = True
    return copy.to_bytes()
