"""Hinge geometry and comic seam policy, including unequal page shapes."""
from types import SimpleNamespace as NS
import unittest

from logisticsmobile.fold_layout import seam_fraction, comic_mode, page_region
from features.comics.mobile.composite import spread_geometry
from features.comics.mobile.navigation import ComicNavigation
from Mobile.native_tests.tests.logisticsmobile.reader_parity_probe import image_bytes


class FoldLayoutTests(unittest.TestCase):
    def test_reserved_region_replaces_midpoint_and_orientation_assumptions(self):
        from logisticsmobile.fold_layout import Division
        from unittest.mock import patch
        host = NS(preferences=NS(values={'comic_layout': 'single'}))
        widget = NS(_impl=NS(native=NS(bounds=NS(size=NS(width=900, height=700)))))
        with patch('logisticsmobile.fold_layout.reserved_divisions', return_value=(Division(460, 0, 40, 700),)):
            self.assertAlmostEqual(seam_fraction(host, widget), 480 / 900)
            self.assertEqual(comic_mode(host, widget), 'double')
        with patch('logisticsmobile.fold_layout.reserved_divisions', return_value=()):
            self.assertIsNone(seam_fraction(host, widget, include_open=True))
            self.assertEqual(comic_mode(host, widget), 'single')
        with patch('logisticsmobile.fold_layout.reserved_divisions', return_value=(Division(0, 320, 900, 40),)):
            self.assertIsNone(seam_fraction(host, widget))
            self.assertEqual(page_region(host, widget), (0, 0, 900, 320))
        # A fold outside/partly intersecting a pane does not split that pane.
        with patch('logisticsmobile.fold_layout.reserved_divisions', return_value=(Division(460, 200, 40, 100),)):
            self.assertIsNone(seam_fraction(host, widget))

    def test_workspace_ratios_and_reserved_gaps(self):
        from logisticsmobile.fold_layout import Division
        from logisticsmobile.pane_layout import panes
        flat = panes(960, 700, browser_priority=True)
        self.assertAlmostEqual(flat.leading / (flat.leading + flat.trailing), 1 / 3)
        self.assertEqual(flat.leading + flat.gap + flat.trailing, 960)
        book = panes(960, 700, fold=Division(440, 0, 60, 700), browser_priority=True)
        self.assertEqual((book.axis, book.leading, book.gap, book.trailing), ('row', 440, 60, 460))
        table = panes(700, 960, fold=Division(0, 440, 700, 60))
        self.assertEqual((table.axis, table.leading, table.gap, table.trailing), ('column', 440, 60, 460))
        boox = panes(720, 1000, browser_priority=True)
        self.assertGreater(boox.trailing, boox.leading)
        self.assertGreaterEqual(boox.leading, 180)
        self.assertGreaterEqual(boox.trailing, 320)

    def test_unequal_pages_meet_at_seam_without_distortion(self):
        sizes = [(500, 1000), (800, 1000)]
        size, rects = spread_geometry(sizes, viewport=(1000, 700), seam=.53)
        self.assertEqual(size, (1000, 700))
        left, right = rects
        self.assertEqual(left[0] + left[2], 530)
        self.assertEqual(right[0], 530)
        for source, (_, y, w, h) in zip(sizes, rects):
            self.assertAlmostEqual(w / h, source[0] / source[1], delta=.003)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(y + h, 700)
        size, rects = spread_geometry([sizes[0]], viewport=(1000, 700), seam=.53, single_right=True)
        self.assertEqual(rects[0][0], 530)
        self.assertLessEqual(rects[0][0] + rects[0][2], 1000)

    def test_composed_pixels_have_no_gutter_and_keep_manga_order(self):
        from features.comics.mobile.composite import compose_spread
        red = image_bytes(b'\xff\x00\x00\xff', 100, 200)
        blue = image_bytes(b'\x00\x00\xff\xff', 80, 200)
        for rtl in (False, True):
            image = compose_spread([red, blue], right_to_left=rtl,
                                   viewport=(951, 669), seam=.5)
            pixels = image._impl.native.raw
            center = pixels.width // 2
            self.assertEqual(pixels.getpixel((center - 1, pixels.height // 2)),
                             (0, 0, 255, 255) if rtl else (255, 0, 0, 255))
            self.assertEqual(pixels.getpixel((center, pixels.height // 2)),
                             (255, 0, 0, 255) if rtl else (0, 0, 255, 255))

    def test_wide_image_remains_one_page_and_fits_inside_a_fold_region(self):
        pages = [image_bytes(b'\xff\x00\x00\xff', w, h)
                 for w, h in ((100, 200), (300, 200), (100, 200), (100, 200))]
        nav = ComicNavigation(lambda i: (pages[i], 'image'), len(pages))
        self.assertEqual(nav.load(0, viewport=(1000, 700), mode='double')[0], (0,))
        self.assertEqual(nav.load(1, viewport=(1000, 700), mode='double')[0], (1,))
        self.assertEqual(nav.load(2, viewport=(1000, 700), mode='double')[0], (2, 3))
        size, rects = spread_geometry([(300, 200)], viewport=(1000, 700), seam=.5)
        self.assertEqual(size, (1000, 700))
        self.assertLessEqual(rects[0][0] + rects[0][2], 500)


if __name__ == '__main__':
    unittest.main()
