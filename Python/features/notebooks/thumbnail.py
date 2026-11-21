"""First-page file thumbnails using the bounded notebook overview and native PDF renderer."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from io import BytesIO
from math import isfinite

from commonUtils.runtime.operations import check_cancelled


def notebook_thumbnail(data, edge, *, cancelled):
    from pypdf import PdfReader, PdfWriter, Transformation
    from pypdf.generic import DecodedStreamObject, NameObject
    from features.pdf.document import MAX_PDF, PDFDocument
    from .brushes import NATIVE_HIGHLIGHTS, PALETTE
    from .notebook import Notebook
    from .previews import page_previews
    from .templates import available, geometry, settings, template_name

    book = Notebook.read(data, max_bytes=MAX_PDF)
    check_cancelled(cancelled)
    scene, = page_previews(book, 0, count=1, include_images=False)
    scale = 320 / max(scene['width'], scene['height'])
    width, height = scene['width'] * scale, scene['height'] * scale
    page = book.pages[0]
    writer = PdfWriter()
    cover = writer.add_blank_page(width, height)
    commands = [f'q {scale:g} 0 0 {-scale:g} 0 {height:g} cm', '1 J 1 j']
    redirect = page.record.get('redir', {}).get('value', -1)
    pdf = book.members.get(book.id + '.pdf')
    if pdf and redirect >= 0:
        reader = PdfReader(BytesIO(pdf))
        if not reader.is_encrypted and redirect < len(reader.pages):
            backing = reader.pages[redirect]
            backing.transfer_rotation_to_content()
            box = backing.cropbox
            ratio = min(width / max(1, float(box.width)), height / max(1, float(box.height)))
            cover.merge_transformed_page(backing, Transformation()
                .translate(-float(box.left), -float(box.bottom)).scale(ratio)
                .translate((width - float(box.width) * ratio) / 2, height - float(box.height) * ratio))
    else:
        paper = settings(book, page)
        if paper['visible'] and available(book, page):
            paths, _ = geometry(template_name(page.template), paper['format'])
            commands.append('0.65 G 1.5 w')
            for path in paths:
                _, x, y, _, end_x, end_y = path.split()
                commands.append(f'{x} {y} m {end_x} {end_y} l S')

    for line in scene['items']:
        check_cancelled(cancelled)
        color = line['color_rgba'] or (NATIVE_HIGHLIGHTS.get(line['color']) if line['tool'] == 18 else None)
        if color:
            alpha = color[3] / 255
            rgb = [1 - alpha + alpha * value / 255 for value in color[:3]]
        else:
            rgb = [value / 255 for value in bytes.fromhex(PALETTE.get(line['color'], '#000000')[1:])]
        commands.append(' '.join(f'{value:.4f}' for value in rgb) + ' RG')
        points = line['points']
        # The overview has already sampled and ordered the visible ink.
        for first, last in zip(points, points[1:] or points):
            x, y, _, start_width = first
            end_x, end_y, _, end_width = last
            if first is last:
                end_x += .01  # PDF strokes a dot as a short round-capped segment.
            if all(isfinite(value) for value in (x, y, end_x, end_y, start_width, end_width)):
                weight = max(.75 / scale, (start_width + end_width) / 2)
                commands.append(f'{weight:.4f} w {x:.3f} {y:.3f} m {end_x:.3f} {end_y:.3f} l S')

    commands.append('Q')
    overlay = writer.add_blank_page(width, height)
    stream = DecodedStreamObject()
    stream.set_data('\n'.join(commands).encode('ascii'))
    overlay[NameObject('/Contents')] = writer._add_object(stream.flate_encode())
    cover.merge_page(overlay)
    writer.remove_page(1)
    output = BytesIO()
    writer.write(output)
    check_cancelled(cancelled)
    return PDFDocument.render_page(output.getvalue(), 0, edge=edge)
