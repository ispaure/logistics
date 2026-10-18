"""Palette readability and matching offline document surfaces."""
import unittest
from logisticsmobile.appearance import contrast_ratio
from logisticsmobile.palette import LIGHT, DARK, argb, themed_chapter, css_variables
from logisticsmobile.preview import markdown_preview
from features.lm.mobile.presentation import transcript_document


class AppearanceTests(unittest.TestCase):
    def test_android_inline_surfaces_have_no_opaque_fill_elevation_or_tint(self):
        import sys
        from types import SimpleNamespace as NS
        from unittest.mock import MagicMock, patch
        from logisticsmobile.appearance import paint_surface
        from logisticsmobile.palette import set_eink_enabled
        class Impl:
            __module__ = 'toga_android.widgets.button'
        impl = Impl()
        impl.interface = NS(on_press=lambda: None)
        impl.native = MagicMock()
        impl.native.getResources().getConfiguration().uiMode = 0x20
        impl.scale_in = lambda n: n
        impl._surface_roles = ('transparent', 'text', False)
        impl._surface_eink_outlined = False
        drawable = MagicMock()
        factory = MagicMock(return_value=drawable)
        modules = {'android': NS(R=NS(attr=NS(state_enabled=1))),
                   'android.content.res': NS(ColorStateList=MagicMock()),
                   'android.graphics.drawable': NS(GradientDrawable=factory, RippleDrawable=MagicMock())}
        try:
            with patch.dict(sys.modules, modules):
                for eink in (False, True, False):
                    set_eink_enabled(eink)
                    paint_surface(impl, 0)
                    self.assertEqual(drawable.setColor.call_args.args, (0,))
                    impl.native.setElevation.assert_called_with(0)
                    impl.native.setStateListAnimator.assert_called_with(None)
                    impl.native.setBackgroundTintList.assert_called_with(None)
                    drawable.setStroke.assert_not_called()
        finally:
            set_eink_enabled(False)

    def test_reader_footer_reserves_floating_tab_bar_without_accumulating_padding(self):
        from types import SimpleNamespace as NS
        from toga.style import Pack
        from logisticsmobile.appearance import reserve_navigation
        def rect(y, height, width=400):
            return NS(origin=NS(y=y), size=NS(height=height, width=width))
        native = NS(bounds=rect(0, 800), convertRect=lambda *a, **kw: rect(0, 800))
        view = NS(_reading_frame=True, _reading_frame_owner=NS(margin=16),
                  style=Pack(margin=16), _impl=NS(container=NS(
                      native=native, top_inset=0, bottom_inset=0)))
        bar = NS(isHidden=lambda: False, bounds=rect(720, 80),
                 convertRect=lambda *a, **kw: rect(720, 80))
        app = NS(native_host=NS(adapter=NS(navigation=[], controller=NS(tabBar=bar))),
                 routes=NS(body=lambda: NS(children=[view])), main_window=NS(_impl=NS(native=object())))
        reserve_navigation(app)
        self.assertEqual(view.style.margin_bottom, 96)
        # A Duo rail must release the previous bottom-bar reservation, and a
        # subsequent rotation back to a bottom bar must restore it once.
        bar.convertRect = lambda *a, **kw: rect(204, 574, 52)
        reserve_navigation(app)
        self.assertEqual(view.style.margin_bottom, 16)
        bar.convertRect = lambda *a, **kw: rect(720, 80)
        reserve_navigation(app)
        self.assertEqual(view.style.margin_bottom, 96)
        reserve_navigation(app)
        self.assertEqual(view.style.margin_bottom, 96)
        view._comic_fullscreen = True
        view.style.margin = 0
        reserve_navigation(app)
        self.assertEqual(view.style.margin_bottom, 0)

    def test_user_picker_selection_closes_field_before_dispatching_change(self):
        from types import SimpleNamespace
        from logisticsmobile.appearance import commit_apple_selection
        calls = []
        native = SimpleNamespace(text='Old choice',
                                 resignFirstResponder=lambda: calls.append('dismiss'))
        item = SimpleNamespace(title='New choice')
        def changed():
            self.assertEqual(native.text, 'New choice')
            self.assertEqual(calls, ['dismiss'])
            calls.append('change')
        picker = SimpleNamespace(native=native, interface=SimpleNamespace(
            items=[item], _title_for_item=lambda value: value.title, on_change=changed))
        commit_apple_selection(picker, 0)
        self.assertEqual(calls, ['dismiss', 'change'])
        # Selecting the current row again also dismisses the picker.
        calls.clear()
        commit_apple_selection(picker, 0)
        self.assertEqual(calls, ['dismiss', 'change'])

    def test_apple_picker_reloads_native_rows_before_selecting_replaced_items(self):
        from types import SimpleNamespace
        from logisticsmobile.appearance import select_apple_item
        calls = []
        class Picker:
            count = 1
            def reloadAllComponents(self):
                self.count = 2
                calls.append('reload')
        impl = SimpleNamespace(native_picker=Picker())
        def native_select(impl, index, item):
            self.assertLess(index, impl.native_picker.count)
            calls.append(item)
            return index
        self.assertEqual(select_apple_item(impl, 1, 'LocalCrypt', select=native_select), 1)
        self.assertEqual(calls, ['reload', 'LocalCrypt'])

    def test_text_and_secondary_labels_remain_readable_on_all_surfaces(self):
        for palette in (LIGHT, DARK):
            for surface in ('window', 'surface', 'alternate'):
                for ink in ('text', 'muted'):
                    with self.subTest(palette=palette, surface=surface, ink=ink):
                        self.assertGreaterEqual(contrast_ratio(argb(palette[ink]), argb(palette[surface])), 4.5)
            self.assertGreaterEqual(contrast_ratio(argb(palette['accent']), argb(palette['surface'])), 4.5)

    def test_preview_and_chat_follow_the_same_system_palette(self):
        for html, background in ((markdown_preview('# Notes'), 'surface'), (transcript_document(theme_css=css_variables()), 'chat_background')):
            self.assertIn('@media(prefers-color-scheme:dark)', html)
            for palette in (LIGHT, DARK):
                for role, color in palette.items():
                    self.assertIn(f'--{role}:{color}', html)
            self.assertIn(f'background:var(--{background})', html)

    def test_chat_canvas_tracks_system_light_and_dark_themes(self):
        html = transcript_document(theme_css=css_variables())
        self.assertEqual(LIGHT['chat_background'], '#ffffff')
        self.assertEqual(DARK['chat_background'], '#000000')
        self.assertIn('html { min-height:100%; background:var(--chat_background) }', html)
        self.assertIn('@media(prefers-color-scheme:dark)', html)
        for palette in (LIGHT, DARK):
            self.assertGreaterEqual(contrast_ratio(argb(palette['text']),
                                                   argb(palette['chat_background'])), 4.5)

    def test_explicit_reader_appearance_overrides_device_mode(self):
        content = '<html><head><style>body{margin:24px}</style></head><body>Book</body></html>'
        for mode, palette in (('light', LIGHT), ('dark', DARK)):
            html = themed_chapter(content, mode)
            self.assertIn('body{margin:24px}', html)
            self.assertIn('<body>Book</body>', html)
            self.assertIn('--surface:' + palette['surface'], html)
            self.assertNotIn('@media', html)
