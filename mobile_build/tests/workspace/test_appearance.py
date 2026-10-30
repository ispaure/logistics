"""Palette readability and matching offline document surfaces."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import unittest
from commonUtils.ui.appearance.colors import contrast_ratio
from mobile.palette import LIGHT, DARK, argb, themed_chapter, css_variables
from mobile.preview import markdown_preview
from features.lm.mobile.presentation import transcript_document


class AppearanceTests(unittest.TestCase):
    def test_ios_workspace_group_anchor_supports_method_and_property_getters(self):
        from types import SimpleNamespace as NS
        from mobile.folder_hub_style import tree_anchor

        class Impl:
            __module__ = 'toga_iOS.widgets.label'

        impl = Impl()
        label = NS(_impl=impl, style=NS(margin_left=0))
        for getter in (NS(width=40), lambda: NS(width=40)):
            impl.native = NS(intrinsicContentSize=getter)
            self.assertEqual(tree_anchor(label), 20)
        impl.native = NS(intrinsicContentSize=lambda: NS(width=200))
        self.assertEqual(tree_anchor(label), 32)

    def test_browser_navigation_returns_to_accent_without_losing_eink_outlines(self):
        import sys
        from types import SimpleNamespace as NS
        from unittest.mock import MagicMock, patch
        from mobile.appearance import paint_surface
        from mobile.browser_ui import browser_command
        from mobile.palette import EINK, set_eink_enabled

        class Impl:
            __module__ = 'toga_android.widgets.button'
        class Colors:
            def __new__(cls, states, colors):
                return NS(states=states, colors=colors)
            valueOf = staticmethod(lambda value: value)
        impl = Impl()
        button = NS(_impl=impl, on_press=lambda: None)
        impl.interface, impl.native, impl.scale_in = button, MagicMock(), lambda value: value
        drawable = MagicMock()
        modules = {'android': NS(R=NS(attr=NS(state_enabled=1))),
                   'android.content.res': NS(ColorStateList=Colors),
                   'android.graphics.drawable': NS(GradientDrawable=lambda: drawable,
                                                   RippleDrawable=MagicMock())}
        try:
            with patch.dict(sys.modules, modules):
                for index, (eink, colors) in enumerate(((False, LIGHT), (True, EINK), (False, DARK))):
                    set_eink_enabled(eink)
                    impl.native.getResources().getConfiguration().uiMode = 0x20 if colors is DARK else 0x10
                    drawable.setStroke.reset_mock()
                    if index == 0:
                        browser_command(button)
                    else:
                        paint_surface(impl, 8)
                    drawable.setColor.assert_called_with(0)
                    if eink:
                        drawable.setStroke.assert_called_with(1, argb('#000000'))
                    else:
                        drawable.setStroke.assert_not_called()
                    tint = impl.native.setTextColor.call_args.args[0]
                    self.assertEqual(tint.colors, [argb(colors['muted']), argb(colors['accent'])])
        finally:
            set_eink_enabled(False)

    def test_android_filled_commands_follow_theme_and_preserve_eink_boundary(self):
        import sys
        from types import SimpleNamespace as NS
        from unittest.mock import MagicMock, patch
        from mobile.appearance import outline_command, paint_surface
        from commonUtils.ui.native.appearance import clear_surface_caches
        from mobile.palette import EINK, set_eink_enabled

        class Impl:
            __module__ = 'toga_android.widgets.button'

        impl = Impl()
        # Backend creation happens before interface._impl exists.
        impl.interface = NS(on_press=lambda: None)
        impl.native = MagicMock()
        impl.scale_in = lambda value: value * 2
        drawable = MagicMock()
        class Colors:
            def __new__(cls, states, colors):
                return NS(states=states, colors=colors)
            valueOf = staticmethod(lambda value: value)
        ripple = MagicMock()
        modules = {'android': NS(R=NS(attr=NS(state_enabled=1))),
                   'android.content.res': NS(ColorStateList=Colors),
                   'android.graphics.drawable': NS(GradientDrawable=lambda: drawable,
                                                   RippleDrawable=ripple)}
        try:
            with patch.dict(sys.modules, modules):
                for index, (dark, eink, colors) in enumerate((
                        (False, False, LIGHT), (True, False, DARK),
                        (False, True, EINK), (False, False, LIGHT))):
                    set_eink_enabled(eink)
                    drawable.reset_mock()
                    clear_surface_caches()
                    impl.native.getResources().getConfiguration().uiMode = 0x20 if dark else 0x10
                    if index == 0:
                        outline_command(impl)
                    else:
                        paint_surface(impl, 8)
                    if eink:
                        drawable.setStroke.assert_called_with(2, argb(colors['border']))
                    else:
                        drawable.setStroke.assert_not_called()
                    drawable.setColor.assert_called_with(argb(colors['surface']))
                    # High contrast changes colors/outlines while preserving normal geometry.
                    drawable.setCornerRadius.assert_called_with(16)
                    tint = impl.native.setTextColor.call_args.args[0]
                    self.assertEqual(tint.states, [[-1], []])
                    self.assertEqual(tint.colors, [argb(colors['muted']), argb(colors['text'])])
                    impl.native.setBackgroundTintList.assert_called_with(None)
                    impl.native.setBackground.assert_called_with(
                        ripple.return_value.getConstantState.return_value.newDrawable.return_value.mutate.return_value)
                    impl.native.setSelected.assert_not_called()
        finally:
            set_eink_enabled(False)

    def test_command_boundaries_contrast_with_light_dark_and_chat_surfaces(self):
        from mobile.palette import EINK
        for colors in (LIGHT, DARK, EINK):
            for background in ('surface', 'window', 'alternate', 'chat_background', 'chat_input'):
                if background in colors:
                    with self.subTest(background=background, colors=colors):
                        self.assertGreaterEqual(contrast_ratio(argb(colors['control_border']),
                                                               argb(colors[background])), 3)

    def test_android_alert_dimming_is_applied_before_show_without_changing_completion(self):
        import sys
        from types import SimpleNamespace as NS
        from unittest.mock import Mock, patch
        from mobile.appearance import show_android_dialog
        events = []
        window = NS(addFlags=lambda value: events.append(('flags', value)),
                    setDimAmount=lambda value: events.append(('dim', value)))
        impl = NS(native=NS(getWindow=lambda: window))
        host, future, result = object(), object(), object()
        def show(dialog, owner, completion):
            self.assertIs(dialog, impl)
            self.assertIs(owner, host)
            self.assertIs(completion, future)
            self.assertEqual(events, [('flags', 2), ('dim', .5)])
            return result
        with patch.dict(sys.modules, {'android.view': NS(WindowManager=NS(
                LayoutParams=NS(FLAG_DIM_BEHIND=2)))}):
            self.assertIs(show_android_dialog(impl, host, future, show=show), result)
            # Unsupported picker backends still complete through Toga normally.
            impl.native = None
            fallback = Mock()
            show_android_dialog(impl, host, future, show=fallback)
            fallback.assert_called_once_with(impl, host, future)

    def test_folder_states_have_distinct_shapes_and_readable_light_dark_colors(self):
        from mobile.control_icons import ICONS
        from mobile.palette import EINK
        self.assertNotEqual(ICONS['folder_locked'][2], ICONS['folder_unlocked'][2])
        for colors in (LIGHT, DARK):
            self.assertEqual(colors['folder'], colors['folder_unlocked'])
            self.assertNotEqual(colors['folder_locked'], colors['folder_unlocked'])
            for state in ('folder_locked', 'folder_unlocked'):
                for background in ('surface', 'window'):
                    self.assertGreaterEqual(contrast_ratio(argb(colors[state]), argb(colors[background])), 4.5)
        self.assertEqual(EINK['folder_locked'], EINK['folder_unlocked'])
        self.assertEqual(EINK['folder'], EINK['folder_unlocked'])

    def test_ios_transparent_button_uses_native_color_property(self):
        import sys
        from types import SimpleNamespace as NS
        from unittest.mock import Mock, patch
        from mobile.appearance import paint_surface

        class Impl:
            __module__ = 'toga_iOS.widgets.button'

        # Rubicon exposes UIColor.clearColor as an ObjCInstance, not a method.
        clear = object()
        border = NS(resolvedColorWithTraitCollection=lambda traits: NS(CGColor='border'))
        factory = Mock(return_value=NS(clearColor=clear))
        impl = Impl()
        impl.interface = NS()
        impl.native = NS(layer=NS(), traitCollection=object())
        impl._surface_roles = ('transparent', None, False)
        with patch.dict(sys.modules, {'rubicon.objc': NS(ObjCClass=factory)}), patch.dict(
                'mobile.appearance._apple_palette.colors', border=border):
            paint_surface(impl, 0)
        factory.assert_called_once_with('UIColor')
        self.assertIs(impl.native.backgroundColor, clear)
        self.assertIs(impl._default_background_color, clear)
        self.assertEqual(impl.native.layer.borderWidth, 0)

    def test_android_inline_surfaces_have_no_opaque_fill_elevation_or_tint(self):
        import sys
        from types import SimpleNamespace as NS
        from unittest.mock import MagicMock, patch
        from mobile.appearance import paint_surface
        from mobile.palette import set_eink_enabled
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
        from mobile.appearance import reserve_navigation
        def rect(y, height, width=400):
            return NS(origin=NS(y=y), size=NS(height=height, width=width))
        native = NS(bounds=rect(0, 800), convertRect=lambda *a, **kw: rect(0, 800))
        view = NS(_reading_frame=True, _reading_frame_owner=NS(margin=16),
                  style=Pack(margin=16), _impl=NS(container=NS(
                      native=native, top_inset=0, bottom_inset=0)))
        bar = NS(isHidden=lambda: False, bounds=rect(720, 80),
                 convertRect=lambda *a, **kw: rect(720, 80))
        app = NS(native_host=NS(adapter=NS(navigation=[], controller=NS(tabBar=bar))),
                 routes=NS(body=lambda: NS(children=[view])), main_window=NS(_impl=NS(native=NS(bounds=rect(0, 800), safeAreaInsets=NS(bottom=0)))))
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
        # Modern UIKit hides the active tab container while tabBar.isHidden
        # can still be false. That must release the old floating-bar margin.
        app.native_host.adapter.tabs_hidden = lambda: True
        reserve_navigation(app)
        self.assertEqual(view.style.margin_bottom, 16)
        app.native_host.adapter.tabs_hidden = lambda: False
        reserve_navigation(app)
        self.assertEqual(view.style.margin_bottom, 96)
        bar.convertRect = lambda *a, **kw: rect(204, 574, 52)
        app.main_window._impl.native.safeAreaInsets.bottom = 34
        reserve_navigation(app)
        self.assertEqual(view.style.margin_bottom, 50)
        reserve_navigation(app)
        self.assertEqual(view.style.margin_bottom, 50)
        view._impl.container.bottom_inset = 34
        reserve_navigation(app)
        self.assertEqual(view.style.margin_bottom, 16)
        # Reader buttons retain their full hit area above the home strip.
        view.children = [NS(children=[])]
        view._impl.container.bottom_inset = 0
        reserve_navigation(app)
        self.assertEqual(view.style.margin_bottom, 50)  # 16 frame + 34 home.
        view._impl.container.bottom_inset = 34
        reserve_navigation(app)
        self.assertEqual(view.style.margin_bottom, 16)
        # A passive caption may use the home strip; the transport row may not.
        footer = NS(vertical=False, widget=NS(layout=NS(content_height=69)),
                    row=NS(layout=NS(content_height=48)))
        view.children = [NS(_reader_page_footer=footer)]
        view._impl.container.bottom_inset = 0
        reserve_navigation(app)
        self.assertEqual(view.style.margin_bottom, 29)  # 16 frame + 13 home.
        reserve_navigation(app)
        self.assertEqual(view.style.margin_bottom, 29)
        view._impl.container.bottom_inset = 13
        reserve_navigation(app)
        self.assertEqual(view.style.margin_bottom, 16)
        footer.vertical = True
        view._impl.container.bottom_inset = 0
        reserve_navigation(app)
        self.assertEqual(view.style.margin_bottom, 50)
        view._comic_fullscreen = True
        view.style.margin = 0
        reserve_navigation(app)
        self.assertEqual(view.style.margin_bottom, 0)

    def test_chat_releases_modern_hidden_tab_clearance(self):
        from types import SimpleNamespace as NS
        from toga.style import Pack
        from features.lm.mobile.ui import ChatUI
        def rect(y, height, width=400):
            return NS(origin=NS(y=y), size=NS(height=height, width=width))
        native = NS(bounds=rect(0, 800), convertRect=lambda *a, **kw: rect(0, 800))
        view = NS(style=Pack(margin=12), _impl=NS(container=NS(
            native=native, top_inset=0, bottom_inset=0)))
        tab = NS(isHidden=lambda: False, bounds=rect(720, 80),
                 convertRect=lambda *a, **kw: rect(720, 80))
        adapter = NS(navigation=[], controller=NS(tabBar=tab), tabs_hidden=lambda: False)
        app = NS(native_host=NS(adapter=adapter), chat_view=view,
                 main_window=NS(_impl=NS(native=NS(bounds=rect(0, 800), safeAreaInsets=NS(bottom=0)))))
        ChatUI.reserve_chat_navigation(app)
        self.assertGreater(view.style.margin_bottom, 12)
        adapter.tabs_hidden = lambda: True
        ChatUI.reserve_chat_navigation(app)
        self.assertEqual(view.style.margin_bottom, 12)
        app.main_window._impl.native.safeAreaInsets.bottom = 34
        ChatUI.reserve_chat_navigation(app)
        self.assertEqual(view.style.margin_bottom, 46)
        ChatUI.reserve_chat_navigation(app)
        self.assertEqual(view.style.margin_bottom, 46)
        view._impl.container.bottom_inset = 34
        ChatUI.reserve_chat_navigation(app)
        self.assertEqual(view.style.margin_bottom, 12)

    def test_user_picker_selection_closes_field_before_dispatching_change(self):
        from types import SimpleNamespace
        from mobile.appearance import commit_apple_selection
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
        from mobile.appearance import select_apple_item
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
        for html, background in ((markdown_preview('# Notes'), 'window'), (transcript_document(theme_css=css_variables()), 'chat_background')):
            self.assertIn('@media(prefers-color-scheme:dark)', html)
            for palette in (LIGHT, DARK):
                for role, color in palette.items():
                    self.assertIn(f'--{role}:{color}', html)
            self.assertIn(f'background:var(--{background})', html)
        self.assertIn('html,html body{background:var(--window);color:var(--text)}', markdown_preview('# Notes'))

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
        for mode, palette in (('system', LIGHT), ('light', LIGHT), ('dark', DARK)):
            html = themed_chapter(content, mode)
            self.assertIn('body{margin:24px}', html)
            self.assertIn('<body>Book</body>', html)
            self.assertIn('--surface:' + palette['surface'], html)
            self.assertIn('html,body{background:var(--window);color:var(--text)}', html)
            if mode != 'system':
                self.assertNotIn('@media', html)
        for mode in ('sepia', 'slate'):
            self.assertEqual(themed_chapter(content, mode), content)
