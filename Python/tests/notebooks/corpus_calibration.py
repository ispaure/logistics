"""Synthetic PDF-backed notebook width measurements for corpus preparation."""
from io import BytesIO
from math import isclose
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import NameObject, NumberObject, RectangleObject

from features.notebooks._vendor.rmscene import scene_stream as ss
from features.notebooks.editor import Editor
from features.notebooks.ink import InkPage, encode
from features.notebooks.notebook import Notebook
from features.notebooks.remarkable_export import export_rmdoc
from features.pdf.annotation import notebook_from_pdf
from tests.readers.test_pdf_reader import pdf_bytes

# Independent expectations for this synthetic suite. Keep these separate from
# the brush tables and geometry constants the receipt measures.
PLAIN_SIZE = (1404, 1872)
SCENE_UNITS_PER_POINT = 226 / 72
IMPORTED_WIDTHS = ((3.25, 5.75), (23.5, 27.25))
IMPORTED_X = (620, 660)
INPUT_X = (100, 140)
NEW_STROKES = (
    ('Fineliner thin', 17, 1, 0, 2, 6.25),
    ('Fineliner medium', 17, 2, 0, 3.5, 12.5),
    ('Fineliner thick', 17, 3, 0, 5.25, 19),
    ('Highlighter fixed', 18, 2, 6, 26, 94.25),
)
TOLERANCE = 0.0001  # Native XY coordinates are encoded as float32.


def _pdf_fixture():
    writer = PdfWriter(clone_from=BytesIO(pdf_bytes()))
    writer.add_blank_page(width=300, height=600).rotate(90)
    cropped = writer.add_blank_page(width=300, height=600)
    cropped.cropbox = RectangleObject((25, 55, 265, 535))
    user_unit = writer.add_blank_page(width=150, height=300)
    user_unit[NameObject('/UserUnit')] = NumberObject(2)
    writer.pdf_header = '%PDF-1.6'
    writer.add_blank_page(width=954, height=1696)
    output = BytesIO()
    writer.write(output)
    # Physical point dimensions, including crop, rotation and UserUnit.
    return output.getvalue(), (
        ('portrait-300x600', (300, 600)),
        ('portrait-400x600', (400, 600)),
        ('portrait-500x600', (500, 600)),
        ('rotated-90', (600, 300)),
        ('offset-crop', (240, 480)),
        ('user-unit-2', (300, 600)),
        ('large-954x1696', (954, 1696)),
    )


def _imported_scene():
    page = InkPage.blank()
    page.add([[IMPORTED_X[0], 80, .25], [IMPORTED_X[1], 80, .75]], tool=17)
    page.add([[IMPORTED_X[0], 120, .25], [IMPORTED_X[1], 120, .75]], tool=18, color=6)
    blocks = list(ss.read_blocks(BytesIO(page.to_bytes())))
    lines = [block.item.value for block in blocks if isinstance(block, ss.SceneLineItemBlock)]
    for line, widths in zip(lines, IMPORTED_WIDTHS, strict=True):
        line.thickness_scale = 2.625
        for point, width in zip(line.points, widths, strict=True):
            point.width = round(width * 4)
    return encode(blocks)


def _measure_geometry(editor, expected_bounds):
    width, height = PLAIN_SIZE
    left = min(0, expected_bounds['x']) if expected_bounds else 0
    expected_size = [width - 2 * left, max(height, expected_bounds['height']) if expected_bounds else height]
    # Use the actual Editor payload while leaving PDF rasterization outside this check.
    with patch.object(editor, 'background', return_value=None):
        state = editor.state()
    bounds = editor.pdf_bounds()
    actual_left = editor.canvas_left()
    size = [state['width'], state['height']]
    canvas_bounds = state['pdf_paper']
    if expected_bounds is None:
        bounds_match = bounds is None and canvas_bounds is None
    else:
        expected_canvas_bounds = dict(expected_bounds, x=expected_bounds['x'] - left)
        bounds_match = (bounds is not None and canvas_bounds is not None and
                        all(isclose(actual[key], expected[key], abs_tol=TOLERANCE)
                            for actual, expected in ((bounds, expected_bounds), (canvas_bounds, expected_canvas_bounds))
                            for key in expected))
    expanded = editor.expanded_ink()
    matches = (bounds_match and expanded == (expected_bounds is not None)
               and isclose(actual_left, left, abs_tol=TOLERANCE)
               and all(isclose(actual, expected, abs_tol=TOLERANCE)
                       for actual, expected in zip(size, expected_size, strict=True)))
    return (dict(paper_bounds=bounds, canvas_paper_bounds=canvas_bounds, canvas_size=size,
                 expected_canvas_size=expected_size, canvas_left=actual_left, expanded=expanded, matches=matches),
            state['strokes'])


def _measure_case(name, pdf_points, editors, source_pdf, raw, plain):
    model, saved, exported = editors
    index = model.index
    expanded = name == 'modern'
    width, height = PLAIN_SIZE
    expected_bounds = None
    if expanded:
        paper_width, paper_height = [value * SCENE_UNITS_PER_POINT for value in pdf_points]
        expected_bounds = dict(x=(width - paper_width) / 2, y=0, width=paper_width, height=paper_height)
    model_geometry, canvas_strokes = _measure_geometry(model, expected_bounds)
    geometry = dict(model=model_geometry, saved=_measure_geometry(saved, expected_bounds)[0],
                    exported=_measure_geometry(exported, expected_bounds)[0])
    actual_bounds = geometry['model']['paper_bounds']
    normalization_height = actual_bounds['height'] if actual_bounds else height
    expected_normalization_height = expected_bounds['height'] if expected_bounds else height
    expected_left = min(0, expected_bounds['x']) if expected_bounds else 0
    expected = [('Imported Fineliner', IMPORTED_WIDTHS[0]), ('Imported Highlighter', IMPORTED_WIDTHS[1])]
    expected.extend((tool, (modern if expanded else standard,) * 2)
                    for tool, _, _, _, standard, modern in NEW_STROKES)
    pages = [editor.notebook.page(index) for editor in editors]
    rows = []
    for row_index, ((tool, expected_widths), canvas, stroke, saved_stroke, exported_stroke) in enumerate(
            zip(expected, canvas_strokes, *(page.strokes for page in pages), strict=True)):
        observations = dict(model=stroke.points, canvas=canvas['points'], saved=saved_stroke.points,
                            exported=exported_stroke.points)
        observed = {key: [point[3] for point in points] for key, points in observations.items()}
        if row_index < len(IMPORTED_WIDTHS):
            native_x = IMPORTED_X
            canvas_x = [x - expected_left for x in native_x]
        else:
            canvas_x = INPUT_X
            native_x = [x + expected_left for x in canvas_x]
        x_error = max(abs(point[0] - reference) for stage, points in observations.items()
                      for point, reference in zip(points, canvas_x if stage == 'canvas' else native_x, strict=True))
        plain_widths = plain['strokes'][row_index]['observed']['canvas'] if plain else observed['canvas']
        plain_height = plain['normalization_height'] if plain else normalization_height
        scene_ratio = [actual / control for actual, control in zip(observed['canvas'], plain_widths, strict=True)]
        normalized_ratio = [ratio * plain_height / normalization_height for ratio in scene_ratio]
        error = max(abs(actual - reference) for values in observed.values()
                    for actual, reference in zip(values, expected_widths, strict=True))
        rows.append(dict(tool=tool, expected=list(expected_widths), observed=observed, max_abs_error=error,
                         max_abs_x_error=x_error,
                         width_ratio_to_plain=scene_ratio, height_normalized_ratio_to_plain=normalized_ratio))
    expected_redirect = {'value': index} if source_pdf is not None else None
    archive = dict(imported_scene_preserved=all(page.to_bytes().startswith(raw) for page in pages),
                   scene_matches_save_and_export=all(page.to_bytes() == pages[0].to_bytes() for page in pages[1:]),
                   pdf_preserved=all(editor.notebook.members.get(editor.notebook.id + '.pdf') == source_pdf
                                     for editor in editors),
                   page_mapping_preserved=all(editor.notebook.pages[index].record.get('redir')
                                              == expected_redirect for editor in editors))
    return dict(layout=name, expected_pdf_points=list(pdf_points) if pdf_points else None,
                expected_paper_bounds=expected_bounds, geometry=geometry, archive=archive,
                normalization_height=normalization_height, expected_normalization_height=expected_normalization_height,
                strokes=rows, passed=all(archive.values()) and all(check['matches'] for check in geometry.values())
                and all(row['max_abs_error'] == 0 and row['max_abs_x_error'] <= TOLERANCE for row in rows))


def _run_book(book, name, variants, raw, *, source_pdf=None, plain=None):
    if len(book.pages) != len(variants):
        raise ValueError('Synthetic PDF import changed the fixture page count.')
    for page in book.pages:
        book.members[f'{book.id}/{page.id}.rm'] = raw
        page.ink = None
    book = Notebook.read(book.to_bytes())
    checkpoint = None

    def save(changed):
        nonlocal checkpoint
        checkpoint = changed.to_bytes()

    editor = Editor(book, save)
    for index in range(len(variants)):
        editor.apply(dict(op='page', index=index))
        for row, (_, tool, width, color, _, _) in enumerate(NEW_STROKES):
            y = 200 + 45 * row
            editor.apply(dict(op='stroke', tool=tool, width=width, color=color,
                              points=[[INPUT_X[0], y, .25], [INPUT_X[1], y, .75]]))
    saved = Editor(Notebook.read(checkpoint))
    exported = Editor(Notebook.read(export_rmdoc(book)))
    editors = (editor, saved, exported)
    cases = []
    for index, (fixture, pdf_points) in enumerate(variants):
        for current in editors:
            current.apply(dict(op='page', index=index))
        case = _measure_case(name, pdf_points, editors, source_pdf, raw, plain)
        cases.append(dict(fixture=fixture, **case))
    return cases


def calibrate():
    """Return a JSON-compatible receipt for synthetic scene and geometry checks."""
    pdf, variants = _pdf_fixture()
    raw = _imported_scene()
    cases = _run_book(Notebook.new('Synthetic notebook control'), 'plain', (('plain', None),), raw)
    for layout in ('legacy', 'modern'):
        book = notebook_from_pdf(pdf, 'Synthetic PDF width calibration')
        if layout == 'modern':
            book.content.update(formatVersion=2, zoomMode='fitToHeight', cPages={'pages': []})
            book.content.pop('pages', None)
        cases.extend(_run_book(book, layout, variants, raw, source_pdf=pdf, plain=cases[0]))
    return dict(passed=all(case['passed'] for case in cases), cases=cases,
                scope='Synthetic native scene units and Editor canvas payload geometry through save and portable '
                      'RMDOC export/reopen. Height-normalized ratios model equal paper heights; '
                      'browser pixels, native rendering and physical input require separate acceptance.')
