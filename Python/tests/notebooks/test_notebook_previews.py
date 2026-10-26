"""Overview previews are bounded, respect hidden layers and leave the book alone."""
import base64
import unittest
from xml.etree import ElementTree as ET

from features.notebooks.notebook import Notebook
from features.notebooks.previews import BATCH, page_previews


class PagePreviewTests(unittest.TestCase):
    def test_visible_ink_and_fixed_ranges_do_not_change_page_order_or_bytes(self):
        book = Notebook.new('Overview')
        ink = book.page(0)
        ink.add([[10, 20, .2], [40, 50, .8]], 15, 7, 2)
        ink.add_layer('Hidden')
        hidden = ink.layers[-1][0]
        ink.add([[100, 200, .5], [200, 300, .5]], 17, 6, 2, hidden)
        ink.layers = [(key, name, key != hidden) for key, name, shown in ink.layers]
        for _ in range(BATCH + 2):
            book.add_page()
        book = Notebook.read(book.to_bytes())
        before = book.to_bytes()
        order = [p.id for p in book.pages]
        rows = page_previews(book, 0)
        self.assertEqual(len(rows), BATCH)
        svg = base64.b64decode(rows[0]['image'].split(',', 1)[1])
        paths = ET.fromstring(svg).findall('.//{http://www.w3.org/2000/svg}path')
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0].get('stroke'), '#b33e39')
        self.assertEqual([row['index'] for row in page_previews(book, BATCH)], [BATCH, BATCH + 1, BATCH + 2])
        self.assertEqual([p.id for p in book.pages], order)
        self.assertEqual(book.to_bytes(), before)
        for start in (-1, len(book.pages), True):
            with self.assertRaises(ValueError):
                page_previews(book, start)

    def test_dense_page_preview_is_bounded_and_retains_stroke_endpoints(self):
        book = Notebook.new()
        ink = book.page(0)
        ink.add([[i / 10, i / 10, .5] for i in range(10000)], 17, 0, 2)
        image = base64.b64decode(page_previews(book, 0)[0]['image'].split(',', 1)[1])
        self.assertLess(len(image), 40000)
        self.assertIn(b'999.9,999.9', image)
