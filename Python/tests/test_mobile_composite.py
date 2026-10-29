"""Composite spread geometry stays portable and bounds the native allocation."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import unittest
from features.comics.mobile.composite import spread_geometry, MAX_PIXELS, MAX_SIDE


class CompositeGeometryTests(unittest.TestCase):
    def test_unequal_pages_keep_proportions_at_one_common_height(self):
        size, rects = spread_geometry([(125, 301), (151, 401)])
        self.assertEqual(size[1], 401)
        self.assertEqual(rects[1], (rects[0][2], 0, 151, 401))
        for source, (_, _, width, height) in zip([(125, 301), (151, 401)], rects):
            self.assertLess(abs(width - height * source[0] / source[1]), 1)

    def test_combined_decode_is_bounded_even_when_both_pages_are_large(self):
        for sizes in [[(2000, 4000)] * 2, [(4000, 4001)] * 2, [(1, 8192)] * 2]:
            (width, height), rects = spread_geometry(sizes)
            self.assertLessEqual(width * height, MAX_PIXELS)
            self.assertLessEqual(max(width, height), MAX_SIDE)
            self.assertTrue(all(w > 0 and h > 0 for _, _, w, h in rects))
            self.assertEqual(rects[-1][0] + rects[-1][2], width)

    def test_fitted_spreads_have_no_gutter_across_page_sizes_and_viewports(self):
        # Standard spreads follow the documented zero-gap policy. Physical
        # hinge clearance is a separate seam_gap contract in test_fold_layout.
        for sizes in [[(100, 200)] * 2, [(2000, 4000)] * 2,
                      [(100, 200), (80, 220)], [(4000, 8000)] * 2]:
            for viewport in [(411, 683), (834, 1158), (1200, 500)]:
                with self.subTest(sizes=sizes, viewport=viewport):
                    (width, height), rects = spread_geometry(sizes, viewport=viewport)
                    self.assertEqual(rects[1][0], rects[0][0] + rects[0][2])
                    self.assertEqual(rects[-1][0] + rects[-1][2], width)
                    self.assertLessEqual(width * height, MAX_PIXELS)
                    self.assertLessEqual(max(width, height), MAX_SIDE)

    def test_empty_excess_or_zero_sized_pages_are_rejected(self):
        for sizes in [[], [(1, 2)] * 3, [(0, 2)], [(-1, 2)]]:
            with self.assertRaises(ValueError):
                spread_geometry(sizes)
