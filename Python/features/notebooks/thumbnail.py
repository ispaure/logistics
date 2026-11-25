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


def graphite_thumbnail_density(pressure, mechanical):
    # Cover pixels average the small flecks and the bare paper between them.
    pressure = round(round(pressure * 255) * 32 / 255) / 32
    light_contact = max(0, 1 - ((pressure - .46) / .34) ** 2) ** 2
    lift = .045 if mechanical else .065
    mid_contact = max(0, min((pressure - .57) / .23, (.9375 - pressure) / .1375))
    pencil_contact = max(0, min((pressure - .5) / .07, (.77 - pressure) / .20))
    engagement = pressure + (.12 * mid_contact if mechanical else .085 * mid_contact + .13 * pencil_contact)
    contact = max(0, min(1, (engagement + lift * light_contact - .45) / .55))
    density = .8 * contact ** 2 * (3 - 2 * contact)
    fade = max(0, min(1, (pressure - .39) / .29))
    flecks = .1 * max(0, min(1, (pressure - .1) / .15)) * (1 - fade ** 2 * (3 - 2 * fade))
    return density + (1 - density) * flecks


def notebook_thumbnail(data, edge, *, cancelled, dark=False):
    from pypdf import PdfReader, PdfWriter, Transformation
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    from features.pdf.document import MAX_PDF, PDFDocument
    from .brushes import BRUSHES, NATIVE_HIGHLIGHTS, PALETTE
    from .notebook import Notebook
    from .previews import page_previews
    from .templates import available, geometry, rule_style, settings, template_name

    book = Notebook.read(data, max_bytes=MAX_PDF)
    check_cancelled(cancelled)
    scene, = page_previews(book, 0, count=1, include_images=False)
    scale = 320 / max(scene['width'], scene['height'])
    width, height = scene['width'] * scale, scene['height'] * scale
    page = book.pages[0]
    writer = PdfWriter()
    if dark:
        writer.pdf_header = '%PDF-1.4'
    cover = writer.add_blank_page(width, height)
    fill = f'0 0 {width:g} {height:g} re f'
    paper_stream = DecodedStreamObject()
    paper_stream.set_data(f'q 1 g {fill} Q'.encode('ascii'))
    cover[NameObject('/Contents')] = writer._add_object(paper_stream)
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
            name = template_name(page.template)
            paths, _ = geometry(name, paper['format'])
            color, weight = rule_style(name)
            rgb = [value / 255 for value in bytes.fromhex(color[1:])]
            if dark:
                rgb = [1 - value for value in rgb]
            commands.append(' '.join(f'{value:.4f}' for value in rgb) + f' RG {weight:g} w')
            for path in paths:
                _, x, y, _, end_x, end_y = path.split()
                commands.append(f'{x} {y} m {end_x} {end_y} l S')

    highlights = NameObject('/NotebookHighlight')
    for line in scene['items']:
        check_cancelled(cancelled)
        points = line['points']
        if not points:
            continue
        tool = line['tool']
        color = line['color_rgba'] or (NATIVE_HIGHLIGHTS.get(line['color']) if tool == 18 else None)
        rgb = tuple(color[:3]) if color else tuple(bytes.fromhex(PALETTE.get(line['color'], '#000000')[1:]))
        alpha = color[3] / 255 if color else 1
        if dark and rgb in {(0, 0, 0), (255, 255, 255)}:
            rgb = tuple(255 - value for value in rgb)
        highlight = dark and tool in (5, 18)
        if highlight:
            alpha *= .36
            commands.append(f'q {highlights} gs')
        def stroke_color(pressure=None):
            opacity = alpha
            paper_value = 0 if dark else 1
            if pressure is not None:
                opacity *= graphite_thumbnail_density(pressure, tool in (7, 13))
            components = [paper_value * (1 - opacity) + opacity * value / 255 for value in rgb]
            return ' '.join(f'{value:.4f}' for value in components) + ' RG'

        last_color = stroke_color()
        commands.append(last_color)
        graphite = tool in (1, 7, 13, 14)
        # The overview has already sampled and ordered the visible ink.
        brush_id = {1: 14, 2: 15, 7: 13}.get(tool, tool)
        width_scale = BRUSHES.get(brush_id, {}).get('display_width', 1)
        path = []
        for first, last in zip(points, points[1:] or points):
            x, y, start_pressure, start_width = first
            end_x, end_y, end_pressure, end_width = last
            if first is last:
                end_x += .01  # PDF strokes a dot as a short round-capped segment.
            if all(isfinite(value) for value in (x, y, end_x, end_y, start_width, end_width)):
                if graphite:
                    color_command = stroke_color((start_pressure + end_pressure) / 2)
                    if color_command != last_color:
                        commands.append(color_command)
                        last_color = color_command
                weight = max(.75 / scale, (start_width + end_width) * width_scale / 2)
                segment = f'{x:.3f} {y:.3f} m {end_x:.3f} {end_y:.3f} l'
                if highlight and start_width == end_width == points[0][3]:
                    path.append(segment)
                else:
                    commands.append(f'{weight:.4f} w {segment} S')
        if path:
            weight = max(.75 / scale, points[0][3])
            commands.append(f'{weight:.4f} w ' + ' '.join(path) + ' S')
        if highlight:
            commands.append('Q')

    commands.append('Q')
    overlay = writer.add_blank_page(width, height)
    if dark:
        blend_modes = DictionaryObject({
            highlights: DictionaryObject({NameObject('/BM'): NameObject('/Screen')}),
        })
        if pdf and redirect >= 0:
            # Invert only the background, before emitting ink in its display colors.
            invert = NameObject('/NotebookInvert')
            blend_modes[invert] = DictionaryObject({NameObject('/BM'): NameObject('/Difference')})
            commands.insert(0, f'q {invert} gs 1 g {fill} Q')
        else:
            commands.insert(0, f'q 0 g {fill} Q')
        overlay[NameObject('/Resources')][NameObject('/ExtGState')] = blend_modes
    stream = DecodedStreamObject()
    stream.set_data('\n'.join(commands).encode('ascii'))
    overlay[NameObject('/Contents')] = writer._add_object(stream.flate_encode())
    cover.merge_page(overlay)
    writer.remove_page(1)
    output = BytesIO()
    writer.write(output)
    check_cancelled(cancelled)
    return PDFDocument.render_page(output.getvalue(), 0, edge=edge)
