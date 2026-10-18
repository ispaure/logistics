"""E Ink selection stays visible even when the native theme disables indicators."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

from logisticsmobile.navigation import eink_selection_indicator


class NavigationContrastTests(unittest.TestCase):
    def test_square_indicator_and_theme_restoration_for_both_presentations(self):
        for presentation in ('bottom', 'rail'):
            for density in (1, 2.75):
                with self.subTest(presentation=presentation, density=density):
                    bar = Mock()
                    bar.isItemActiveIndicatorEnabled.return_value = False
                    bar.getItemActiveIndicatorWidth.return_value = 64
                    bar.getItemActiveIndicatorHeight.return_value = 32
                    shape = bar.getItemActiveIndicatorShapeAppearance.return_value
                    bar.getResources().getDisplayMetrics().density = density
                    model = Mock()
                    with patch.dict('sys.modules', {
                        'com.google.android.material.shape': NS(ShapeAppearanceModel=model),
                    }):
                        original = eink_selection_indicator(bar, True)
                        bar.setItemActiveIndicatorEnabled.assert_called_with(True)
                        bar.setItemActiveIndicatorWidth.assert_called_with(round(40 * density))
                        bar.setItemActiveIndicatorHeight.assert_called_with(round(40 * density))
                        bar.setItemActiveIndicatorShapeAppearance.assert_called_with(
                            model.builder().build())
                        # Reapplying must not replace the saved theme with E Ink geometry.
                        self.assertIs(eink_selection_indicator(bar, True, original), original)
                    self.assertIsNone(eink_selection_indicator(bar, False, original))
                    bar.setItemActiveIndicatorEnabled.assert_called_with(False)
                    bar.setItemActiveIndicatorWidth.assert_called_with(64)
                    bar.setItemActiveIndicatorHeight.assert_called_with(32)
                    bar.setItemActiveIndicatorShapeAppearance.assert_called_with(shape)

    def test_normal_appearance_without_saved_indicator_keeps_native_geometry(self):
        bar = Mock()
        self.assertIsNone(eink_selection_indicator(bar, False))
        self.assertEqual(bar.mock_calls, [])
