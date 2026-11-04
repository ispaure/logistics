"""Compact browser columns follow full viewport and fold geometry."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

import unittest
from mobile.pane_layout import browser_columns


class MobileBrowserColumnsTests(unittest.TestCase):
    def test_exterior_and_narrow_inner_windows_share_compact_browser(self):
        for bounds in ((420, 900), (500, 650), (800, 1100), (600, 400), (678, 466)):
            self.assertFalse(browser_columns(*bounds))
        self.assertTrue(browser_columns(1100, 800))
        self.assertTrue(browser_columns(951, 669))
        self.assertTrue(browser_columns(600, 800, fold=object()))
