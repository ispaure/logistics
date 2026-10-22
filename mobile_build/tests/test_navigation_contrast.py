"""E Ink selection stays visible even when the native theme disables indicators."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

from mobile.navigation import eink_selection_indicator, install_android_navigation_appearance


class NavigationContrastTests(unittest.TestCase):
    def setUp(self):
        self.window = NS(app=NS())
        self.rail_factory = patch('mobile.navigation.create_android_destination_rail')
        self.create_rail = self.rail_factory.start()
        self.addCleanup(self.rail_factory.stop)

    def test_initial_tablet_rail_is_top_aligned_without_an_activity_bar(self):
        activity, rail = Mock(), Mock()
        self.create_rail.return_value = rail
        activity.getSupportActionBar.return_value = None
        adapter = NS(mode='rail', rail=rail, impl=NS(_native_activity=activity),
                     set_mode=Mock())
        with patch.dict('sys.modules', {'android.view': NS(Gravity=NS(TOP=48))}):
            install_android_navigation_appearance(NS(adapter=adapter, window=self.window))
            rail.setMenuGravity.assert_called_once_with(48)
            # Repeated installation must not wrap callbacks or touch geometry.
            install_android_navigation_appearance(NS(adapter=adapter, window=self.window))
            rail.setMenuGravity.assert_called_once_with(48)

    def test_rail_created_after_theme_application_inverts_only_the_checked_icon(self):
        from mobile.appearance import refresh_android_navigation
        from mobile.palette import argb, set_eink_enabled

        class Colors:
            def __init__(self, states, colors):
                self.states, self.colors = states, colors
            valueOf = staticmethod(lambda value: value)

        bottom, rail = Mock(), Mock()
        self.create_rail.return_value = rail
        for bar in (bottom, rail):
            bar.getResources().getDisplayMetrics().density = 1
            bar.isItemActiveIndicatorEnabled.return_value = False
            bar.getItemActiveIndicatorWidth.return_value = 64
            bar.getItemActiveIndicatorHeight.return_value = 32
        activity = Mock()
        adapter = NS(mode='bottom', bottom=bottom, rail=None,
                     impl=NS(_native_activity=activity))
        def set_mode(mode):
            adapter.mode = mode
            if mode == 'rail':
                adapter.rail = rail
        adapter.set_mode = set_mode
        host = NS(adapter=adapter, window=self.window, state=NS(destination='documents'),
                  root=NS(_impl=NS(get_theme_color=lambda role: argb('#ffffff' if role == 4 else '#000000'))))
        modules = {'android': NS(R=NS(attr=NS(state_checked=1, textColorPrimary=2, colorAccent=3))),
                   'android.view': NS(Gravity=NS(TOP=48)),
                   'android.content.res': NS(ColorStateList=Colors),
                   'com.google.android.material': NS(R=NS(attr=NS(colorSurface=4))),
                   'com.google.android.material.shape': NS(ShapeAppearanceModel=Mock())}
        try:
            with patch.dict('sys.modules', modules):
                set_eink_enabled(True)
                refresh_android_navigation(host)
                install_android_navigation_appearance(host)
                activity.getSupportActionBar().hide.assert_called_once_with()
                wrapper = adapter.set_mode
                install_android_navigation_appearance(host)
                self.assertIs(adapter.set_mode, wrapper)
                adapter.set_mode('rail')
                rail.setMenuGravity.assert_called_with(48)
                rail.setItemActiveIndicatorEnabled.assert_called_with(True)
                rail.setItemActiveIndicatorWidth.assert_not_called()
                rail.setItemActiveIndicatorHeight.assert_not_called()
                rail.setItemActiveIndicatorColor.assert_called_with(argb('#000000'))
                rail.setRailDividerColor.assert_called_with(argb('#000000'))
                bottom.setRailDividerColor.assert_not_called()
                tint = rail.setItemIconTintList.call_args.args[0]
                self.assertEqual(tint.states, [[1], []])
                self.assertEqual(tint.colors, [argb('#ffffff'), argb('#000000')])
                self.assertEqual(host.state.destination, 'documents')
                rail.getMenu.assert_not_called()  # Tint the existing artwork, preserving its alpha.
                self.create_rail.assert_called_once_with(host)
                adapter.set_mode('bottom')
                set_eink_enabled(False)
                refresh_android_navigation(host)
                for bar in (bottom, rail):
                    bar.setItemActiveIndicatorEnabled.assert_called_with(False)
                    bar.setItemActiveIndicatorWidth.assert_called_with(64)
                    bar.setItemActiveIndicatorHeight.assert_called_with(32)
                rail.setRailDividerColor.assert_called_with(0)
        finally:
            set_eink_enabled(False)

    def test_rotation_keeps_new_rail_hidden_while_document_is_open(self):
        activity, bottom, rail = Mock(), Mock(), Mock()
        self.create_rail.return_value = rail
        activity.getSupportActionBar.return_value = None
        adapter = NS(mode='bottom', bottom=bottom, rail=None,
                     impl=NS(_native_activity=activity, native_navigationview=bottom))
        def set_mode(mode):
            adapter.mode = mode
            adapter.rail = rail
            adapter.impl.native_navigationview = rail
        adapter.set_mode = set_mode
        self.window.app._document_tabs_hidden = True
        host = NS(adapter=adapter, window=self.window)
        with patch.dict('sys.modules', {'android.view': NS(Gravity=NS(TOP=48))}), patch(
                'mobile.appearance.refresh_android_navigation'):
            install_android_navigation_appearance(host)
            bottom.setVisibility.assert_called_with(8)
            adapter.set_mode('rail')
            rail.setVisibility.assert_called_with(8)

    def test_initial_rail_replacement_rebinds_through_normal_transitions(self):
        activity, old_rail, new_rail = Mock(), Mock(), Mock()
        activity.getSupportActionBar.return_value = None
        self.create_rail.return_value = new_rail
        adapter = NS(mode='rail', rail=old_rail, impl=NS(_native_activity=activity))
        transitions = []

        def set_mode(mode):
            transitions.append((mode, adapter.rail))
            adapter.mode = mode

        adapter.set_mode = set_mode
        host = NS(adapter=adapter, window=self.window)
        with patch.dict('sys.modules', {'android.view': NS(Gravity=NS(TOP=48))}):
            install_android_navigation_appearance(host)
        self.assertEqual(transitions, [('bottom', old_rail), ('rail', new_rail)])
        self.assertIs(adapter.rail, new_rail)
        self.assertEqual(adapter.mode, 'rail')

    def test_rail_factory_preserves_menu_ids_names_and_independent_icons(self):
        self.rail_factory.stop()
        from mobile.navigation import DESTINATION_ITEMS, create_android_destination_rail
        rail, bottom, constructor = Mock(), Mock(), Mock()
        constructor.return_value = rail
        items = [Mock() for _ in DESTINATION_ITEMS]
        icons = [Mock() for _ in DESTINATION_ITEMS]
        rail.getMenu().add.side_effect = items
        bottom.getMenu().getItem.side_effect = [NS(getIcon=lambda icon=icon: icon) for icon in icons]
        host = NS(destinations=[item[0] for item in DESTINATION_ITEMS],
                  labels=[item[1] for item in DESTINATION_ITEMS],
                  adapter=NS(bottom=bottom, impl=NS(_native_activity=Mock())))
        with patch.dict('sys.modules', {
            'android.view': NS(ContextThemeWrapper=Mock()),
            'com.google.android.material': NS(R=NS(style=NS(Theme_MaterialComponents_DayNight=1))),
            'java': NS(jclass=Mock(return_value=constructor)),
        }):
            self.assertIs(create_android_destination_rail(host), rail)
        self.assertEqual(constructor.call_args.args[1], 5)
        for index, (item, icon, label) in enumerate(zip(items, icons, host.labels)):
            self.assertEqual(rail.getMenu().add.call_args_list[index].args, (0, index + 1, index, label))
            item.setContentDescription.assert_called_once_with(label)
            item.setIcon.assert_called_once_with(icon.getConstantState().newDrawable().mutate())

    def test_indicator_shape_and_size_survive_contrast_and_theme_restoration(self):
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
                        bar.setItemActiveIndicatorWidth.assert_not_called()
                        bar.setItemActiveIndicatorHeight.assert_not_called()
                        bar.setItemActiveIndicatorShapeAppearance.assert_not_called()
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
