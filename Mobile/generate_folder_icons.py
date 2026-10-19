"""Regenerate passive folder indicators from the shared vector source (Pillow).

Run from any directory with the desktop development interpreter. Native mobile
controls and desktop Qt use the vectors directly; these PNGs serve ImageViews.
"""
import argparse
from base64 import b64encode
from io import BytesIO
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Python'))

from services.folders.appearance import FOLDER_FILLS, FOLDER_PATHS, FOLDER_STROKE_WIDTH


def render(name):
    from PIL import Image, ImageDraw

    # Supersample the 24-point drawing, including round joins and caps, then
    # retain a 3x PNG for the native template-image adapters to tint.
    scale = 12
    image = Image.new('RGBA', (24 * scale, 24 * scale))
    draw = ImageDraw.Draw(image)
    width = round(FOLDER_STROKE_WIDTH * scale)
    radius = width / 2
    for line in FOLDER_PATHS[name]:
        points = [(x * scale, y * scale) for x, y in line]
        draw.line(points, fill='black', width=width)
        for x, y in points:
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill='black')
    for index, contour in enumerate(FOLDER_FILLS.get(name, ())):
        draw.polygon([(x * scale, y * scale) for x, y in contour],
                     fill='black' if index == 0 else (0, 0, 0, 0))
    output = BytesIO()
    image.resize((72, 72), Image.Resampling.LANCZOS).save(output, format='PNG')
    return b64encode(output.getvalue()).decode('ascii')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Fail if generated indicators are stale.')
    args = parser.parse_args()
    path = ROOT / 'Python/logisticsmobile/hub_icons.py'
    original = path.read_text(encoding='utf-8')
    updated = original
    for name in ('folder_locked', 'folder_unlocked'):
        updated, count = re.subn(
            rf"(    '{name}': ')[^']+(',)",
            lambda match: match[1] + render(name) + match[2], updated)
        if count != 1:
            raise ValueError(f'Expected exactly one generated {name} entry in {path}')
    if args.check:
        if updated != original:
            parser.exit(1, 'Folder indicators are stale; run Mobile/generate_folder_icons.py.\n')
        print('Folder indicators match the shared artwork.')
    else:
        path.write_text(updated, encoding='utf-8')
        print(f'Updated folder indicators in {path}')


if __name__ == '__main__':
    main()
