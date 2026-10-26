"""Workspaces retain host-specific palette and control placement."""
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import MagicMock, patch
from mobile import appearance


class WorkspaceSurfacesTests(TestCase):
    def test_ios_icon_refresh_and_repaint_keep_disclosure_space(self):
        from mobile.control_icons import button_icons
        class Impl:
            __module__ = 'toga_iOS.widgets.button'
        impl = Impl()
        impl.native = MagicMock()
        impl._content_trailing_inset = 32
        button = NS(_impl=impl, on_press=lambda: None)
        impl.interface = button
        bridge = NS(ObjCClass=lambda name: NS(mainScreen=NS(scale=2)),
                    UIEdgeInsets=lambda *values: values)
        with patch.dict('sys.modules', {'rubicon.objc': bridge}), patch(
                'commonUtils.ui.native.icons.apple_symbols', return_value=object()), patch.object(
                appearance, 'apple_color', return_value=MagicMock()):
            button_icons(button, [('storage_local', 'Local')])
            self.assertEqual(impl.native.contentEdgeInsets, (0, 12, 0, 32))
            appearance.surface(button, background='transparent')
            self.assertEqual(impl.native.contentEdgeInsets, (0, 12, 0, 32))


    def test_startup_labels_do_not_gain_tight_high_contrast_borders(self):
        from mobile.startup import StartupScreen
        screen = StartupScreen()
        labels = [screen.status, screen.detail, screen.view.children[0].children[0]]
        self.assertTrue(all(not label._impl._surface_eink_outlined for label in labels))

    def test_selected_row_inverts_all_child_roles_and_restores_normal_theme(self):
        import toga
        row = toga.Box()
        title, icon = toga.Button('Title'), toga.Button('Icon')
        row.add(title, icon)
        appearance.selection_row(row, True, ((title, 'text'), (icon, 'folder_locked')))
        with patch.object(appearance, 'eink_enabled', return_value=True), patch.object(
                appearance._surface_painter, 'paint') as paint:
            appearance.paint_surface(icon._impl, 0)
            self.assertEqual(paint.call_args.args[1].foreground, 'text')
        with patch.object(appearance, 'eink_enabled', return_value=False), patch.object(
                appearance._surface_painter, 'paint') as paint:
            appearance.paint_surface(icon._impl, 0)
            self.assertEqual(paint.call_args.args[1].foreground, 'folder_locked')
        appearance.selection_row(row, False, ((title, 'text'), (icon, 'folder_locked')))
        self.assertFalse(title._impl._surface_eink_selected)
        self.assertFalse(icon._impl._surface_eink_selected)

    def test_tile_selection_includes_icon_but_preserves_photo_preview(self):
        import toga
        from mobile.browser_ui import entry_icon, highlight_entry
        glyph, photo = entry_icon(True), toga.ImageView()
        title = appearance.surface(toga.Button('Folder'), foreground='text')
        card = toga.Box(children=[toga.Box(children=[glyph, photo]), title])
        highlight_entry(card, True)
        self.assertTrue(glyph._impl._surface_eink_selected)
        self.assertTrue(title._impl._surface_eink_selected)
        self.assertFalse(hasattr(photo._impl, '_surface_eink_selected'))
        highlight_entry(card, False)
        self.assertFalse(glyph._impl._surface_eink_selected)

    def test_current_chapter_selection_keeps_accessibility_and_child_contrast(self):
        import toga
        row = toga.Box()
        row.title_button, row.disclosure = toga.Button('Chapter'), toga.Button('Expand')
        from mobile.browser_ui import entry_icon
        glyph = entry_icon(True)
        row.add(row.title_button, row.disclosure, glyph)
        appearance.hierarchy_row_style(row, True)
        self.assertTrue(row._impl._surface_eink_selected)
        self.assertTrue(row.title_button._impl._surface_eink_selected)
        self.assertTrue(row.disclosure._impl._surface_eink_selected)
        self.assertTrue(glyph._impl._surface_eink_selected)
        self.assertEqual(row.title_button.style.font_weight, 'bold')

    def test_selected_template_icon_repaint_uses_white_for_semantic_icon_roles(self):
        from mobile.control_icons import tint_android
        from mobile.palette import LIGHT, argb
        native = MagicMock()
        native.getResources.return_value.getConfiguration.return_value.uiMode = 0
        impl = NS(native=native, _surface_roles=('transparent', 'folder_locked', False),
                  _surface_eink_selected=True, _control_drawable=MagicMock())
        with patch('mobile.palette.eink_enabled', return_value=True), patch(
                'mobile.palette.android_palette', return_value=LIGHT), patch(
                'commonUtils.ui.native.appearance.android_color_states') as colors:
            tint_android(impl)
        colors.assert_called_once_with(argb('#ffffff'), argb('#ffffff'))
