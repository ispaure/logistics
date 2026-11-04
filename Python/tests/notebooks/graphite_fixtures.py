"""Original synthetic graphite strokes; never user handwriting or tablet assets."""
import math
from io import BytesIO
from zipfile import ZipFile
from unittest.mock import patch

from features.notebooks.notebook import Notebook
from features.notebooks.templates import select


def graphite_notebook():
    book = Notebook.new('Synthetic graphite appearance')
    select(book, 0, 'Logistics Lined medium', 'pro', True)
    for tool, offset in ((14, 80), (13, 180)):
        points = [[40 + i * 4, offset + math.sin(i / 7) * 18, .15 + .8 * i / 64]
                  for i in range(65)]
        book.page(0).add(points, tool=tool, width=3)
    return Notebook.read(book.to_bytes())


def archive_members(data):
    with ZipFile(BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def snapshot_export(book, when=1_700_000_000):
    """Compare export bytes with identical clock input, without changing fields."""
    from features.notebooks.remarkable_export import export_rmdoc
    with patch('features.notebooks.notebook.time.time', return_value=when):
        return export_rmdoc(book)
