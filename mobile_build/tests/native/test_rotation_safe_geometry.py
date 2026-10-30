"""Compact headers retain independent title, hardware and side-rail bounds."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from mobile_build.native_tests.tests.logisticsmobile import rotation_checks


def rectangle(x, y, width, height):
    return NS(origin=NS(x=x, y=y), size=NS(width=width, height=height))


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
