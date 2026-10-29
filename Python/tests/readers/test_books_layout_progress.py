"""Whole-book page arithmetic never substitutes chapter or resource weights."""
import unittest
from features.books.locations import LayoutPages


class LayoutProgressTests(unittest.TestCase):
    def test_unequal_chapters_spreads_and_boundary_seeks(self):
        pages = LayoutPages(3)
        pages.reset('portrait')
        pages.record(0, 2)
        self.assertFalse(pages.complete)
        self.assertIsNone(pages.position(0, 1)['fraction'])
        pages.record(1, 7)
        pages.record(2, 1)
        self.assertEqual(pages.position(1, 2)['text'], '50% · Page 5 of 10 · Chapter 2 of 3')
        self.assertEqual(pages.position(1, 2, 2)['text'], '60% · Page 5–6 of 10 · Chapter 2 of 3')
        self.assertEqual(pages.position(2, 0)['text'], '100% · Page 10 of 10 · Chapter 3 of 3')
        self.assertEqual(pages.locate(0), (0, 0))
        self.assertEqual(pages.locate(.2), (1, 0))
        self.assertEqual(pages.locate(1), (2, 0))
        self.assertEqual(pages.boundaries, [0, .2, .9, 1])

    def test_layout_change_discards_old_counts_and_pending_totals_cannot_seek(self):
        pages = LayoutPages(1)
        pages.reset('portrait'); pages.record(0, 12)
        self.assertFalse(pages.reset('portrait'))
        self.assertTrue(pages.complete)
        self.assertTrue(pages.reset('landscape'))
        self.assertEqual(pages.counts, [None])
        with self.assertRaises(ValueError):
            pages.locate(.5)
        with self.assertRaises(ValueError):
            pages.record(0, True)
