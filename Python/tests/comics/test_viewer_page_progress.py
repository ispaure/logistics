"""Progress describes source pages rather than temporary rendered slides."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import unittest
from features.comics.reading import page_progress
from features.comics.mobile.navigation import ComicNavigation
from mobile.pane_layout import browser_columns


class ViewerPageProgressTests(unittest.TestCase):
    def test_visible_page_ranges_are_stable_in_both_visual_orders(self):
        self.assertEqual(page_progress((68, 69), 250), '69 & 70 / 250')
        self.assertEqual(page_progress((69, 68), 250), '69 & 70 / 250')
        self.assertEqual(page_progress((249,), 250), '250 / 250')
        self.assertEqual(page_progress((0,), 250), '1 / 250')

    def test_half_is_shown_beside_source_page_before_total(self):
        navigation = ComicNavigation(None, 250)
        navigation.page, navigation.visible, navigation.split = 68, (68,), True
        self.assertEqual(navigation.progress_label, '69 1/2 / 250')
        navigation.half = 1
        self.assertEqual(navigation.progress_label, '69 2/2 / 250')
        navigation.split = False
        self.assertEqual(navigation.progress_label, '69 / 250')

    def test_exterior_and_narrow_inner_windows_share_compact_browser(self):
        for bounds in ((420, 900), (500, 650), (800, 1100), (600, 400), (678, 466)):
            self.assertFalse(browser_columns(*bounds))
        self.assertTrue(browser_columns(1100, 800))
        self.assertTrue(browser_columns(951, 669))
        self.assertTrue(browser_columns(600, 800, fold=object()))
