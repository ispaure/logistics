"""Hinge geometry and comic seam policy, including unequal page shapes."""
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

from logisticsmobile.fold_layout import seam_fraction, comic_mode
from features.comics.mobile.composite import spread_geometry
from features.comics.mobile.navigation import ComicNavigation
from Mobile.native_tests.tests.logisticsmobile.reader_parity_probe import image_bytes


class FoldLayoutTests(unittest.TestCase):
    def host(self, status=2, orientation=3):
        window = NS(bounds=NS(size=NS(width=1000)), windowScene=NS(interfaceOrientation=orientation))
        host = NS(_hinge_status=status, main_window=NS(_impl=NS(native=window)),
                  preferences=NS(values={'comic_layout': 'single'}))
        native = Mock()
        native.convertRect.return_value = NS(origin=NS(x=20), size=NS(width=900))
        return host, NS(_impl=NS(native=native))

    def test_window_center_accounts_for_asymmetric_rail_and_safe_area(self):
        host, widget = self.host()
        self.assertAlmostEqual(seam_fraction(host, widget), 480 / 900)
        self.assertEqual(comic_mode(host, widget), 'double')
        host._hinge_status = 3
        self.assertIsNone(seam_fraction(host, widget))
        self.assertEqual(comic_mode(host, widget), 'single')
        host._hinge_status = 0
        self.assertIsNone(seam_fraction(host, widget))
        host._hinge_status = 2
        host.main_window._impl.native.windowScene.interfaceOrientation = 1
        self.assertIsNone(seam_fraction(host, widget))

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

    def test_landscape_image_spans_instead_of_becoming_half_a_spread(self):
        pages = [image_bytes(b'\xff\x00\x00\xff', w, h)
                 for w, h in ((100, 200), (300, 200), (100, 200), (100, 200))]
        nav = ComicNavigation(lambda i: (pages[i], 'image'), len(pages))
        self.assertEqual(nav.load(0, viewport=(1000, 700), mode='double')[0], (0,))
        self.assertEqual(nav.load(1, viewport=(1000, 700), mode='double')[0], (1,))
        self.assertEqual(nav.load(2, viewport=(1000, 700), mode='double')[0], (2, 3))
        size, rects = spread_geometry([(300, 200)], viewport=(1000, 700), seam=.5)
        self.assertEqual(size, (300, 200))
        self.assertEqual(rects, [(0, 0, 300, 200)])


if __name__ == '__main__':
    unittest.main()
