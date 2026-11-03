"""Compact headers retain independent title, hardware and side-rail bounds."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from mobile_build.native_tests.tests.logisticsmobile import rotation_checks
from mobile.reader_edges import compact_apple_reader


def rectangle(x, y, width, height):
    return NS(origin=NS(x=x, y=y), size=NS(width=width, height=height))


class ReaderTitleLayoutTests(unittest.TestCase):
    def test_promoted_actions_include_dynamic_toolbar_provider_results(self):
        first, second, third = object(), object(), object()
        calls = []
        def actions():
            calls.append('resolved')
            return (second,)
        widget = NS(title_actions=[first], _ios_toolbar_buttons=actions,
                    _ios_toolbar_leading=(third,))
        self.assertEqual(list(rotation_checks.promoted_controls(widget)), [first, second, third])
        self.assertEqual(calls, ['resolved'])
        self.assertEqual(list(rotation_checks.promoted_controls(NS())), [])

    def setUp(self):
        edge = patch('mobile.ios_toolbar.vertical_edge', return_value=2)
        self.edge = edge.start()
        self.addCleanup(edge.stop)

    def fixture(self, *, vertical, side, safe_top):
        footer = NS(vertical=vertical, widget=NS(layout=NS(content_height=64)),
                    row=NS(layout=NS(content_height=44)))
        window = NS(safeAreaInsets=NS(top=safe_top, bottom=34))
        native = NS(window=window, bounds=rectangle(0, 0, 900, 600),
                    safeAreaInsets=NS(bottom=34),
                    convertRect=lambda *a, **kw: rectangle(0, 0, 900, 600))
        container = NS(native=native, top_inset=82, bottom_inset=34)
        view = NS(_reader_page_footer=footer, _impl=NS(container=container), children=[])
        if side:
            view._document_title_header = NS(parent=view)
        container.content = NS(interface=NS(app=NS(body=NS(children=[view])), children=[view]))
        return container

    def test_reader_header_reclaims_the_bar_strip_but_preserves_hardware_clearance(self):
        for vertical in (False, True):
            for safe_top in (0, 24):
                with self.subTest(vertical=vertical, safe_top=safe_top):
                    container = self.fixture(vertical=vertical, side=True, safe_top=safe_top)
                    with patch('mobile.appearance.reserve_navigation'):
                        compact_apple_reader(container)
                    self.assertEqual(container.top_inset, safe_top)
                    self.assertEqual(container.bottom_inset, 34 if vertical else 14)

    def test_horizontal_navigation_retains_its_system_inset(self):
        container = self.fixture(vertical=False, side=False, safe_top=0)
        with patch('mobile.appearance.reserve_navigation'):
            compact_apple_reader(container)
        self.assertEqual(container.top_inset, 82)

    def test_pane_title_does_not_reclaim_horizontal_native_action_targets(self):
        self.edge.return_value = 0
        container = self.fixture(vertical=False, side=True, safe_top=24)
        with patch('mobile.appearance.reserve_navigation'):
            compact_apple_reader(container)
        self.assertEqual(container.top_inset, 82)

    def test_midpoint_footer_allows_only_its_selected_lower_touch_padding(self):
        container = self.fixture(vertical=False, side=True, safe_top=0)
        footer = container.content.interface.children[0]._reader_page_footer
        footer.row.layout.content_height = 48
        footer.widget.layout.content_height = 66
        footer.slider = NS(_reader_track_offset=14)
        footer.spacer = NS(layout=NS(content_height=16))
        footer.badge = NS(style=NS(margin_top=2))
        window = container.native.window
        window.bounds = rectangle(0, 0, 900, 600)
        window.safeAreaInsets.left = window.safeAreaInsets.right = 0
        with patch('mobile.appearance.reserve_navigation'):
            compact_apple_reader(container)
        row_bottom = 600 - container.bottom_inset - (66 - 48)
        self.assertEqual(row_bottom, 572)  # Six points below the safe edge at 566.
        with self.assertRaises(AssertionError):
            rotation_checks.assert_control_bounds(
                rectangle(4, row_bottom - 48, 48, 48), window, 'Ordinary control')
        rotation_checks.assert_control_bounds(
            rectangle(4, row_bottom - 48, 48, 48), window, 'Previous page', bottom_extension=6)
        with self.assertRaises(AssertionError):
            rotation_checks.assert_control_bounds(
                rectangle(4, row_bottom - 46, 48, 48), window, 'Previous page', bottom_extension=6)

    def test_new_reader_compacts_before_the_selected_route_changes(self):
        container = self.fixture(vertical=False, side=True, safe_top=0)
        app = container.content.interface.app
        app.body = NS(children=[NS(_impl=NS(container=object()))])
        with patch('mobile.appearance.reserve_navigation') as reserve:
            self.assertTrue(compact_apple_reader(container))
        self.assertEqual(container.top_inset, 0)
        reserve.assert_called_once_with(app, view=container.content.interface.children[0])


class RotationSafeGeometryTests(unittest.TestCase):
    def fixture(self, *, y=49.333, width=382, title_y=6):
        window = NS(bounds=rectangle(0, 0, 466, 678),
                    safeAreaInsets=NS(left=0, right=0, top=0, bottom=0))
        container_native = NS(bounds=rectangle(0, 0, 466, 678),
                              safeAreaInsets=NS(left=0, right=84, top=82, bottom=0),
                              convertRect=lambda bounds, **kwargs: rectangle(0, 0, 466, 678))
        height = min(615, 678 - y)
        body_native = NS(bounds=rectangle(0, 0, width, height),
                         convertRect=lambda bounds, **kwargs: rectangle(0, y, width, height))
        title = NS(bounds=rectangle(0, 0, 200, 37.333), superview=object(),
                   convertRect=lambda bounds, **kwargs: rectangle(0, title_y, 200, 37.333))
        controller = NS(navigationItem=NS(titleView=title, prompt=None))
        view = NS(_impl=NS(native=body_native, container=NS(native=container_native)))
        return NS(body=NS(children=[view]), main_window=NS(_impl=NS(native=window)),
                  native_host=NS(adapter=NS(content_controller=lambda destination: controller),
                                 state=NS(destination='documents')))

    def check(self, app, *, compact=True):
        with patch('mobile.ios_content_background.preview_edge', return_value=0), \
                patch('mobile.reader_edges.page_footer', return_value=NS() if compact else None), \
                patch('mobile.ios_toolbar.vertical_edge', return_value=True), \
                patch.object(rotation_checks.sys, 'platform', 'ios'):
            return rotation_checks.safe_geometry(app)

    def test_compact_reader_uses_real_title_clearance_instead_of_old_nav_inset(self):
        report = self.check(self.fixture())
        self.assertAlmostEqual(report['reader_title_content_gap'], 6)
        self.assertLess(report['y'], report['top'])

    def test_content_cannot_overlap_the_compact_title(self):
        with self.assertRaises(AssertionError):
            self.check(self.fixture(y=42))

    def test_compact_title_cannot_enter_hardware_clearance(self):
        with self.assertRaises(AssertionError):
            self.check(self.fixture(title_y=-2))

    def test_compact_reader_still_respects_side_rail(self):
        with self.assertRaises(AssertionError):
            self.check(self.fixture(width=400))

    def test_nonreader_keeps_the_standard_navigation_inset(self):
        with self.assertRaises(AssertionError):
            self.check(self.fixture(), compact=False)
        self.check(self.fixture(y=82), compact=False)
