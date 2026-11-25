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


def picture_xobject(writer, data, header):
    from pypdf.filters import FlateDecode
    from pypdf.generic import DecodedStreamObject, DictionaryObject, EncodedStreamObject, NameObject, NumberObject
    from .images import validate_png

    def image(stream, gray):
        stream.update({NameObject('/Type'): NameObject('/XObject'), NameObject('/Subtype'): NameObject('/Image'),
                       NameObject('/Width'): NumberObject(header.width), NameObject('/Height'): NumberObject(header.height),
                       NameObject('/BitsPerComponent'): NumberObject(8),
                       NameObject('/ColorSpace'): NameObject('/DeviceGray' if gray else '/DeviceRGB')})
        return stream

    stream = EncodedStreamObject()
    if header.format == 'jpeg':
        stream._data = data
        stream[NameObject('/Filter')] = NameObject('/DCTDecode')
        return writer._add_object(image(stream, False))

    channels, compressed = validate_png(data, collect_idat=True)
    parameters = DictionaryObject({NameObject('/Predictor'): NumberObject(15),
        NameObject('/Colors'): NumberObject(channels), NameObject('/Columns'): NumberObject(header.width)})
    if channels in (1, 3):
        stream._data = compressed
        stream[NameObject('/Filter')] = NameObject('/FlateDecode')
        stream[NameObject('/DecodeParms')] = parameters
        return writer._add_object(image(stream, channels == 1))

    pixels = FlateDecode.decode(compressed, parameters)
    alpha, colors = DecodedStreamObject(), DecodedStreamObject()
    alpha.set_data(pixels[channels - 1::channels])
    rgb = bytearray(header.width * header.height * (channels - 1))
    for i in range(channels - 1):
        rgb[i::channels - 1] = pixels[i::channels]
    colors.set_data(bytes(rgb))
    stream = image(colors.flate_encode(), channels == 2)
    stream[NameObject('/SMask')] = writer._add_object(image(alpha.flate_encode(), True))
    return writer._add_object(stream)


def notebook_thumbnail(data, edge, *, cancelled, dark=False):
    from pypdf import PdfReader, PdfWriter, Transformation
    from pypdf.errors import PdfReadError
    from pypdf.generic import DecodedStreamObject, DictionaryObject, FloatObject, NameObject
    from commonUtils.formats.image_headers import image_header
    from features.pdf.document import MAX_PDF, PDFDocument
    from .brushes import BRUSHES, DARK_INK_COLORS, NATIVE_HIGHLIGHTS, PALETTE
    from .editor import Editor
    from .images import picture_assets
    from .notebook import Notebook
    from .previews import page_previews
    from .remarkable_export import BackgroundConversionError, merge_pdf_template, pdf_template_line
    from .templates import TemplateLine, TemplatePDF, page_artwork, settings

    book = Notebook.read(data, max_bytes=MAX_PDF)
    check_cancelled(cancelled)
    editor = Editor(book)
    scene, = page_previews(book, 0, count=1, pdf_bounds=editor.pdf_bounds,
                           include_image_sources=False, include_background=False)
    scale = 320 / max(scene['width'], scene['height'])
    width, height = scene['width'] * scale, scene['height'] * scale
    page = book.pages[0]
    writer = PdfWriter()
    writer.pdf_header = '%PDF-1.4'
    cover = writer.add_blank_page(width, height)
    fill = f'0 0 {width:g} {height:g} re f'
    paper_stream = DecodedStreamObject()
    paper_stream.set_data(f'q 1 g {fill} Q'.encode('ascii'))
    cover[NameObject('/Contents')] = writer._add_object(paper_stream)
    commands = [f'q {scale:g} 0 0 {-scale:g} 0 {height:g} cm', '1 J 1 j']
    redirect = page.record.get('redir', {}).get('value', -1)
    pdf = book.members.get(book.id + '.pdf')
    pdf_background = bool(pdf and redirect >= 0)
    if pdf_background:
        reader = PdfReader(BytesIO(pdf))
        if not reader.is_encrypted and redirect < len(reader.pages):
            backing = reader.pages[redirect]
            backing.transfer_rotation_to_content()
            box = backing.cropbox
            paper = scene['pdf_paper'] or dict(x=0, y=0, width=scene['width'], height=scene['height'])
            ratio = scale * min(paper['width'] / max(1, float(box.width)), paper['height'] / max(1, float(box.height)))
            cover.merge_transformed_page(backing, Transformation()
                .translate(-float(box.left), -float(box.bottom)).scale(ratio)
                .translate((paper['x'] + paper['width'] / 2) * scale - float(box.width) * ratio / 2,
                           height - (paper['y'] + paper['height'] / 2) * scale - float(box.height) * ratio / 2))
    else:
        paper = settings(book, page)
        if paper['visible']:
            artwork = page_artwork(book, page, paper) or ()
            if isinstance(artwork, TemplatePDF):
                try:
                    merge_pdf_template(cover, artwork, scale=scale, left=0, height=scene['height'], sources={})
                    pdf_background = True
                except BackgroundConversionError:
                    pass
            else:
                commands.extend(pdf_template_line(item, dark=dark) for item in artwork if isinstance(item, TemplateLine))

    highlights = NameObject('/NotebookHighlight')
    blend_modes, xobjects = DictionaryObject(), DictionaryObject()
    read_picture = picture_assets(book, 0)
    pictures = {picture.id: picture for picture in book.page(0).images}
    image_budget, pixel_budget = 12 * 1024 * 1024, 16 * 1024 * 1024
    resources = {}
    for line in scene['items']:
        check_cancelled(cancelled)
        if 'corners' in line:
            picture = pictures[line['id']]
            if picture.resource not in resources:
                try:
                    asset = read_picture(picture)
                    header = image_header(asset, max_bytes=image_budget)
                    pixels = header.width * header.height
                    if pixels > pixel_budget or header.format not in ('png', 'jpeg'):
                        continue
                    name = NameObject(f'/NotebookImage{len(xobjects)}')
                    xobjects[name] = picture_xobject(writer, asset, header)
                    resources[picture.resource] = name
                    image_budget -= len(asset)
                    pixel_budget -= pixels
                except (ValueError, PdfReadError):
                    continue
            a, b, _, d = line['corners']
            matrix = (b[0] - a[0], b[1] - a[1], a[0] - d[0], a[1] - d[1], *d)
            commands.append('q ' + ' '.join(f'{v:.4f}' for v in matrix) + f' cm {resources[picture.resource]} Do Q')
            continue
        if 'rectangles' in line:
            rgb = (255, 255, 255) if dark and tuple(line['rgb']) == (0, 0, 0) else line['rgb']
            key = NameObject(f'/TextHighlight{round(line["opacity"] * 1000)}')
            if key not in blend_modes:
                blend_modes[key] = DictionaryObject({NameObject('/ca'): FloatObject(line['opacity']),
                    NameObject('/BM'): NameObject('/Screen' if dark else '/Multiply')})
            color = ' '.join(f'{component / 255:.4f}' for component in rgb)
            rectangles = ' '.join(' '.join(f'{v:.4f}' for v in rect) + ' re' for rect in line['rectangles'])
            commands.append(f'q {key} gs {color} rg {rectangles} f Q')
            continue
        points = line['points']
        if not points:
            continue
        tool = line['tool']
        color = line['color_rgba'] or (NATIVE_HIGHLIGHTS.get(line['color']) if tool == 18 else None)
        rgb = tuple(color[:3]) if color else tuple(bytes.fromhex(PALETTE.get(line['color'], '#000000')[1:]))
        alpha = color[3] / 255 if color else 1
        if dark and rgb in {(0, 0, 0), (255, 255, 255)}:
            rgb = tuple(255 - value for value in rgb)
        elif dark and tool not in (5, 18):
            rgb = DARK_INK_COLORS.get(','.join(map(str, rgb)), rgb)
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
        blend_modes[highlights] = DictionaryObject({NameObject('/BM'): NameObject('/Screen')})
        if pdf_background:
            # Invert only the background, before emitting ink in its display colors.
            invert = NameObject('/NotebookInvert')
            blend_modes[invert] = DictionaryObject({NameObject('/BM'): NameObject('/Difference')})
            commands.insert(0, f'q {invert} gs 1 g {fill} Q')
        else:
            commands.insert(0, f'q 0 g {fill} Q')
    if blend_modes:
        overlay[NameObject('/Resources')][NameObject('/ExtGState')] = blend_modes
    if xobjects:
        overlay[NameObject('/Resources')][NameObject('/XObject')] = xobjects
    stream = DecodedStreamObject()
    stream.set_data('\n'.join(commands).encode('ascii'))
    overlay[NameObject('/Contents')] = writer._add_object(stream.flate_encode())
    cover.merge_page(overlay)
    writer.remove_page(1)
    output = BytesIO()
    writer.write(output)
    check_cancelled(cancelled)
    return PDFDocument.render_page(output.getvalue(), 0, edge=edge)
