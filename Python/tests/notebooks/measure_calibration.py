"""Extract aggregate native brush measurements; keep output under ignored evidence.

Reads user-supplied archives/PDFs without changing them. It emits counts, numeric
ranges and hashes, never handwriting coordinates or cover notes. Sample pages
follow the version-2, twelve-page calibration worksheet.
"""
import argparse
from collections import Counter
from hashlib import sha256
from pathlib import Path
import json
from statistics import median

from pypdf import PdfReader
from features.notebooks.brushes import TOOLS
from features.notebooks.notebook import Notebook


def measure(archive, pdf):
    archive_data, pdf_data = archive.read_bytes(), pdf.read_bytes()
    book = Notebook.read(archive_data)
    reader = PdfReader(pdf)
    if len(book.pages) != 12 or len(reader.pages) != 12:
        raise ValueError('Use the complete twelve-page version-2 calibration worksheet.')
    expected = (17, 15, 14, 13, 16, 12, 21, 18, 23)
    rows = []
    for index, tool in enumerate(expected, 1):
        ink = book.page(index)
        if ink.warning:
            raise ValueError(f'Page {index + 1} cannot be measured: {ink.warning}')
        strokes = [stroke for stroke in ink.strokes if stroke.tool == tool]
        for scale in sorted({s.scale for s in strokes}):
            group = [s for s in strokes if s.scale == scale]
            points = [p for s in group for p in s.points]
            rows.append(dict(page=index + 1, tool=tool, native_scale=scale,
                strokes=len(group), points=len(points),
                width_min=min(p[3] for p in points), width_median=median(p[3] for p in points),
                width_max=max(p[3] for p in points),
                pressure_min=min(p[2] for p in points), pressure_max=max(p[2] for p in points)))
    palette = []
    for index in (10, 11):
        ink = book.page(index)
        if ink.warning:
            raise ValueError(f'Color page {index + 1} cannot be measured: {ink.warning}')
        counts = Counter((s.tool, s.color, s.color_rgba) for s in ink.strokes)
        palette.append(dict(page=index + 1, native=[dict(tool=key[0], color=key[1], rgba=key[2], strokes=n)
                                                    for key, n in counts.items()]))
    all_ink = [book.page(i) for i in range(12)]
    if any(ink.warning for ink in all_ink):
        raise ValueError('Unsupported ink must be preserved rather than silently omitted.')
    roundtrip = Notebook.read(book.to_bytes())
    assert all(roundtrip.page(i).to_bytes() == ink.to_bytes() for i, ink in enumerate(all_ink))
    return dict(archive_sha256=sha256(archive_data).hexdigest(), pdf_sha256=sha256(pdf_data).hexdigest(),
                pages=12, strokes=sum(len(ink.strokes) for ink in all_ink),
                tools=TOOLS, brush_measurements=rows, native_colors=palette,
                unchanged_ink_roundtrip=True,
                limits='Single tablet/firmware; task/tilt/speed confound pressure-dependent width ranges.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = measure(args.archive, args.pdf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    print(f'Measured {report["strokes"]} native strokes on twelve pages; original ink roundtrip verified.')
