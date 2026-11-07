"""Overview scenes are bounded, preserve brush data and leave the book alone."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import unittest

from features.notebooks.notebook import Notebook
from features.notebooks.previews import BATCH, BATCH_POINTS, POINTS, page_previews


class PagePreviewTests(unittest.TestCase):
    def test_visible_ink_and_fixed_ranges_do_not_change_page_order_or_bytes(self):
        book = Notebook.new('Overview')
        ink = book.page(0)
        first = ink.add([[10, 20, .2], [40, 50, .8]], 15, 7, 2)
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
        self.assertEqual(len(rows[0]['items']), 1)
        item = rows[0]['items'][0]
        self.assertEqual((item['tool'], item['color']), (15, 7))
        self.assertEqual([p[3] for p in item['points']], [p[3] for p in first.points])
        self.assertEqual([row['index'] for row in page_previews(book, BATCH)], [BATCH, BATCH + 1, BATCH + 2])
        self.assertEqual([p.id for p in book.pages], order)
        self.assertEqual(book.to_bytes(), before)
        for start in (-1, len(book.pages), True):
            with self.assertRaises(ValueError):
                page_previews(book, start)

    def test_dense_page_preview_is_bounded_and_retains_stroke_endpoints(self):
        book = Notebook.new()
        samples = [[i / 10, i / 10, .5] for i in range(10000)]
        for i in range(3):
            if i:
                book.add_page()
            stroke = book.page(i).add(samples[:2], 17, 0, 2)
            stroke.points = [[x, y, pressure, 3.5] for x, y, pressure in samples]
        rows = page_previews(book, 0)
        self.assertEqual([row['index'] for row in rows], [0, 1])
        self.assertLessEqual(sum(len(row['items'][0]['points']) for row in rows), BATCH_POINTS)
        for row in [*rows, *page_previews(book, 2)]:
            points = row['items'][0]['points']
            self.assertLessEqual(len(points), POINTS)
            self.assertEqual(points[0][:2], [0, 0])
            self.assertEqual(points[-1][:2], [999.9, 999.9])

    def test_native_colors_and_rgba_reach_the_renderer_in_scene_order(self):
        book = Notebook.new()
        ink = book.page(0)
        for choice in (13, 10, 5, 6, -1, 1):
            ink.add([[10, 20, .5], [40, 50, .8]], tool=18, color=choice)
        shader = ink.add([[30, 20, .5]], tool=23, color=6)
        ink.order = [shader.id, *[s.id for s in ink.strokes if s.id != shader.id]]
        items = page_previews(book, 0)[0]['items']
        self.assertEqual((items[0]['tool'], items[0]['color_rgba']), (23, (48, 74, 224, 77)))
        self.assertEqual([item['color'] for item in items[1:]], [3, 4, 5, 14, 15, 16])
        self.assertTrue(all(item['color_rgba'] is None for item in items[1:]))
