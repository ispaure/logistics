"""Hinge geometry and comic seam policy, including unequal page shapes."""
from types import SimpleNamespace as NS
import unittest

from mobile.fold_layout import seam_fraction, reading_seam, comic_mode, page_region
from features.comics.mobile.composite import spread_geometry
from features.comics.mobile.navigation import ComicNavigation
from mobile_build.native_tests.tests.logisticsmobile.reader_parity_probe import image_bytes


class FoldLayoutTests(unittest.TestCase):
    def test_reserved_region_replaces_midpoint_and_orientation_assumptions(self):
        from mobile.fold_layout import Division
        from unittest.mock import patch
        host = NS(preferences=NS(values={'comic_layout': 'single'}))
        widget = NS(_impl=NS(native=NS(bounds=NS(size=NS(width=900, height=700)))))
        with patch('mobile.fold_layout.reserved_divisions', return_value=(Division(460, 0, 40, 700),)):
            self.assertAlmostEqual(seam_fraction(host, widget), 480 / 900)
            self.assertEqual(comic_mode(host, widget), 'double')
        with patch('mobile.fold_layout.reserved_divisions', return_value=()):
            self.assertIsNone(seam_fraction(host, widget, include_open=True))
            self.assertEqual(comic_mode(host, widget), 'single')
        with patch('mobile.fold_layout.reserved_divisions', return_value=(Division(0, 320, 900, 40),)):
            self.assertIsNone(seam_fraction(host, widget))
            self.assertEqual(page_region(host, widget), (0, 0, 900, 320))
        # A fold outside/partly intersecting a pane does not split that pane.
        with patch('mobile.fold_layout.reserved_divisions', return_value=(Division(460, 200, 40, 100),)):
            self.assertIsNone(seam_fraction(host, widget))

    def test_workspace_ratios_and_reserved_gaps(self):
        from mobile.fold_layout import Division
        from mobile.pane_layout import panes
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
        duo = panes(960, 700, browser_priority=True, leading_fraction=.4)
        self.assertAlmostEqual(duo.leading / (duo.leading + duo.trailing), .4)
        self.assertEqual(panes(960, 700, fold=Division(440, 0, 60, 700),
                               leading_fraction=.4), book)

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
        self.assertEqual(left[3], right[3])
        size, rects = spread_geometry([sizes[0]], viewport=(1000, 700), seam=.53, single_right=True)
        self.assertEqual(size, sizes[0])
        self.assertEqual(rects, [(0, 0, *sizes[0])])

    def test_flat_crease_does_not_anchor_or_resize_workspace_pages(self):
        from mobile.fold_layout import Division
        from unittest.mock import patch
        widget = NS(_impl=NS(native=NS(bounds=NS(size=NS(width=900, height=700)))))
        inactive = Division(520, 0, 40, 700)
        def regions(widget, *, include_inactive=False):
            return (inactive,) if include_inactive else ()
        with patch('mobile.fold_layout.reserved_divisions', side_effect=regions):
            self.assertIsNone(reading_seam(None, widget))
        with patch('mobile.fold_layout.reserved_divisions', return_value=(inactive,)):
            self.assertEqual(reading_seam(None, widget), .6)

    def test_sidebar_and_page_order_never_give_matching_pages_unequal_heights(self):
        for sizes in ([(400, 600)] * 2, [(800, 1200), (400, 600)], [(400, 600), (410, 600)]):
            for seam in (.35, .5, .65):
                for order in (sizes, list(reversed(sizes))):
                    _, rects = spread_geometry(order, viewport=(900, 700), seam=seam, seam_gap=24)
                    self.assertEqual(rects[0][3], rects[1][3])
                    self.assertEqual(rects[0][1], rects[1][1])
                    self.assertGreaterEqual(rects[0][0], 0)
                    self.assertLessEqual(rects[1][0] + rects[1][2], 900)

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

    def test_wide_image_remains_one_page_and_fits_the_landscape_view(self):
        pages = [image_bytes(b'\xff\x00\x00\xff', w, h)
                 for w, h in ((100, 200), (300, 200), (100, 200), (100, 200))]
        nav = ComicNavigation(lambda i: (pages[i], 'image'), len(pages))
        self.assertEqual(nav.load(0, viewport=(1000, 700), mode='double')[0], (0,))
        self.assertEqual(nav.load(1, viewport=(1000, 700), mode='double')[0], (1,))
        self.assertEqual(nav.load(2, viewport=(1000, 700), mode='double')[0], (2, 3))
        for seam in (.48, .5, .53):
            for anchor_right in (False, True):
                size, rects = spread_geometry([(300, 200)], viewport=(1000, 700),
                                             seam=seam, single_right=anchor_right, seam_gap=30)
                self.assertEqual(size, (300, 200))
                self.assertEqual(rects, [(0, 0, 300, 200)])

    def test_wide_page_pixels_span_the_fold_in_both_reading_directions(self):
        from features.comics.mobile.composite import compose_spread
        page = image_bytes(b'\xff\x00\x00\xff', 300, 200)
        for rtl in (False, True):
            image = compose_spread([page], right_to_left=rtl, anchor_right=True,
                                   viewport=(1000, 700), seam=.5, seam_gap=30)
            pixels = image._impl.native.raw
            self.assertEqual(pixels.size, (300, 200))
            for x in (0, 149, 150, 299):
                self.assertEqual(pixels.getpixel((x, 100)), (255, 0, 0, 255))
        size, rects = spread_geometry([(300, 200)], viewport=(700, 1000),
                                     seam=.5, single_right=True, seam_gap=30)
        self.assertEqual(size, (300, 200))
        self.assertEqual(rects, [(0, 0, 300, 200)])


if __name__ == '__main__':
    unittest.main()


class EpubFoldGeometryTests(unittest.TestCase):
    def test_epub_crease_is_normalized_in_its_own_view(self):
        from unittest.mock import patch
        from mobile.fold_layout import Division, epub_geometry
        widget = NS(_impl=NS(native=NS(bounds=NS(size=NS(width=1000, height=700)))))
        with patch('mobile.fold_layout.reserved_divisions', return_value=(Division(530, 0, 40, 700),)):
            self.assertEqual(epub_geometry(widget), {'seam': .55, 'gap': .04})
        with patch('mobile.fold_layout.reserved_divisions', return_value=(Division(0, 320, 1000, 40),)):
            self.assertIsNone(epub_geometry(widget))
        with patch('mobile.fold_layout.reserved_divisions', return_value=()):
            self.assertIsNone(epub_geometry(widget))

    def test_crease_changes_reach_imported_and_private_bridges_without_resize(self):
        from unittest.mock import Mock, patch
        from mobile.fold_layout import bind_epub_geometry, sync_epub_geometry
        from features.books.mobile.presentation import ChapterBridge
        views = [Mock(), Mock()]
        for view in views:
            view._chapter_bridge = ChapterBridge(view, root='https://logistics.invalid/test/')
        with patch('mobile.fold_layout.epub_geometry', return_value=None) as geometry:
            for view in views:
                bind_epub_geometry(view)
                view._chapter_bridge.loaded(view)
                view.evaluate_javascript.reset_mock()
            app = NS(readers=NS(controllers={'a': NS(epub_view=views[0])}),
                     private_sessions=NS(controllers={'b': NS(provider_epub_view=NS(webview=views[1]))}))
            geometry.return_value = {'seam': .55, 'gap': .04}
            sync_epub_geometry(app)
            for view in views:
                view.evaluate_javascript.assert_called_once_with(
                    'window.reader && window.reader.setGeometry({"seam": 0.55, "gap": 0.04})')
                view.evaluate_javascript.reset_mock()
            sync_epub_geometry(app)
            for view in views:
                view.evaluate_javascript.assert_not_called()
            geometry.return_value = None
            sync_epub_geometry(app)
            for view in views:
                view.evaluate_javascript.assert_called_once_with('window.reader && window.reader.setGeometry(null)')
