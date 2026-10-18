"""E Ink selection stays visible even when the native theme disables indicators."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

from logisticsmobile.navigation import eink_selection_indicator, install_android_navigation_appearance


class NavigationContrastTests(unittest.TestCase):
    def test_rail_created_after_theme_application_inverts_only_the_checked_icon(self):
        from logisticsmobile.appearance import refresh_android_navigation
        from logisticsmobile.palette import argb, set_eink_enabled

        class Colors:
            def __init__(self, states, colors):
                self.states, self.colors = states, colors
            valueOf = staticmethod(lambda value: value)

        bottom, rail = Mock(), Mock()
        for bar in (bottom, rail):
            bar.getResources().getDisplayMetrics().density = 1
            bar.isItemActiveIndicatorEnabled.return_value = False
            bar.getItemActiveIndicatorWidth.return_value = 64
            bar.getItemActiveIndicatorHeight.return_value = 32
        adapter = NS(mode='bottom', bottom=bottom, rail=None)
        def set_mode(mode):
            adapter.mode = mode
            if mode == 'rail':
                adapter.rail = rail
        adapter.set_mode = set_mode
        host = NS(adapter=adapter, state=NS(destination='documents'),
                  root=NS(_impl=NS(get_theme_color=lambda role: argb('#ffffff' if role == 4 else '#000000'))))
        modules = {'android': NS(R=NS(attr=NS(state_checked=1, textColorPrimary=2, colorAccent=3))),
                   'android.content.res': NS(ColorStateList=Colors),
                   'com.google.android.material': NS(R=NS(attr=NS(colorSurface=4))),
                   'com.google.android.material.shape': NS(ShapeAppearanceModel=Mock())}
        try:
            with patch.dict('sys.modules', modules):
                set_eink_enabled(True)
                refresh_android_navigation(host)
                install_android_navigation_appearance(host)
                wrapper = adapter.set_mode
                install_android_navigation_appearance(host)
                self.assertIs(adapter.set_mode, wrapper)
                adapter.set_mode('rail')
                rail.setItemActiveIndicatorEnabled.assert_called_with(True)
                rail.setItemActiveIndicatorWidth.assert_called_with(40)
                rail.setItemActiveIndicatorHeight.assert_called_with(40)
                rail.setItemActiveIndicatorColor.assert_called_with(argb('#000000'))
                tint = rail.setItemIconTintList.call_args.args[0]
                self.assertEqual(tint.states, [[1], []])
                self.assertEqual(tint.colors, [argb('#ffffff'), argb('#000000')])
                self.assertEqual(host.state.destination, 'documents')
                rail.getMenu.assert_not_called()  # Tint the existing artwork, preserving its alpha.
                adapter.set_mode('bottom')
                set_eink_enabled(False)
                refresh_android_navigation(host)
                for bar in (bottom, rail):
                    bar.setItemActiveIndicatorEnabled.assert_called_with(False)
                    bar.setItemActiveIndicatorWidth.assert_called_with(64)
                    bar.setItemActiveIndicatorHeight.assert_called_with(32)
        finally:
            set_eink_enabled(False)

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
