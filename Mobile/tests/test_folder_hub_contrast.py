"""Workspaces keeps a single row outline and a visible monochrome selection."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

from logisticsmobile import appearance, folder_hub_style, palette


class FolderHubContrastTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(palette.set_eink_enabled, False)
        self.drawable = Mock()
        modules = {
            'android': NS(R=NS(attr=NS(state_enabled=1))),
            'android.graphics.drawable': NS(GradientDrawable=self.drawable,
                                            RippleDrawable=lambda *args: args),
            'android.content.res': NS(ColorStateList=NS(
                valueOf=lambda value: value)),
        }
        # Android's constructor and valueOf overloads are both used by surfaces.
        class Colors:
            def __new__(cls, *args):
                return args

            valueOf = staticmethod(lambda value: value)

        modules['android.content.res'].ColorStateList = Colors
        self.modules = patch.dict('sys.modules', modules)
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def widget(self, *, button=True):
        impl = type('AndroidWidget', (), {'__module__': 'toga_android.widgets'})()
        impl.native = Mock()
        impl.native.getResources.return_value.getConfiguration.return_value.uiMode = 0
        impl.scale_in = lambda value: value
        widget = NS(_impl=impl, style=NS(margin_left=0, margin_right=0, margin_top=0, margin_bottom=0), children=[])
        if button:
            widget.on_press = None
        impl.interface = widget
        return widget

    def test_tree_group_anchor_uses_the_native_ios_size_getter(self):
        impl = type('IOSLabel', (), {'__module__': 'toga_iOS.widgets.label'})()
        impl.native = NS(intrinsicContentSize=lambda: NS(width=28, height=18))
        label = NS(_impl=impl, text='A long group heading', style=NS(font_size=15))
        self.assertEqual(folder_hub_style.tree_anchor(label), 14)
        impl.native.intrinsicContentSize = lambda: NS(width=200, height=18)
        self.assertEqual(folder_hub_style.tree_anchor(label), folder_hub_style.TREE_INDENT - 8)

    def test_tree_segments_do_not_accumulate_fractional_rounding(self):
        import toga
        from toga.style import Pack
        label = toga.Label('Lib', style=Pack(font_size=15, margin_left=8))
        self.assertEqual(folder_hub_style.tree_anchor(label), 19)
        guide = folder_hub_style.tree_guide(210, (24, 182), 30)
        top = 0
        centers = []
        for segment in guide.children:
            height = segment.style.height
            self.assertEqual(height, round(height))
            if height == folder_hub_style.TREE_STROKE:
                centers.append(top + height / 2)
                self.assertEqual(segment.style.margin_left + segment.style.width, 40)
            top += height
        self.assertEqual(centers, [24, 182])
        self.assertEqual(top, 210)

    def test_source_selection_inverts_only_in_high_contrast_and_repaints(self):
        tab = self.widget()
        palette.set_eink_enabled(True)
        folder_hub_style.source_tab(tab, True)
        self.drawable.return_value.setColor.assert_called_with(palette.argb('#000000'))
        tab._impl.native.setTextColor.assert_called_with((
            [[-1], []], [palette.argb('#ffffff'), palette.argb('#ffffff')]))
        self.drawable.return_value.setStroke.assert_not_called()

        # Repainting existing controls after toggling restores Slate colours.
        palette.set_eink_enabled(False)
        appearance.paint_surface(tab._impl, 8)
        self.drawable.return_value.setColor.assert_called_with(palette.argb(palette.LIGHT['surface']))
        palette.set_eink_enabled(True)
        folder_hub_style.source_tab(tab, False)
        self.drawable.return_value.setColor.assert_called_with(palette.argb('#ffffff'))

    def test_shared_surface_rows_and_titles_remain_borderless_in_monochrome(self):
        palette.set_eink_enabled(True)
        folder_hub_style.folder_row(self.widget(button=False))
        self.drawable.return_value.setStroke.assert_not_called()
        self.drawable.reset_mock()
        folder_hub_style.surface(self.widget(), outlined=False)
        self.drawable.return_value.setStroke.assert_not_called()
        title = self.widget()
        original = title._impl.native.getBackground.return_value
        folder_hub_style.folder_name(title)
        self.drawable.return_value.setStroke.assert_not_called()
        palette.set_eink_enabled(False)
        appearance.restore_eink_button(title._impl)
        title._impl.native.setBackground.assert_called_with(original)

    def test_regular_folder_title_has_a_transparent_borderless_surface(self):
        title = self.widget()
        folder_hub_style.folder_name(title)
        self.drawable.return_value.setColor.assert_called_with(0)
        self.drawable.return_value.setStroke.assert_not_called()
        title._impl.native.setElevation.assert_called_with(0)

    def test_rows_keep_compact_spacing_inside_shared_group(self):
        palette.set_eink_enabled(True)
        row = self.widget(button=False)
        row.children = [self.widget(), self.widget()]
        folder_hub_style.folder_row(row)
        self.assertEqual(row.style.margin_bottom, folder_hub_style.ROW_GAP)
        self.assertEqual(row.children[0].style.margin_left, 0)
        self.assertEqual(row.children[-1].style.margin_right, 0)
        self.assertTrue(all(child.style.margin_top == child.style.margin_bottom == 0
                            for child in row.children))
        self.drawable.return_value.setStroke.assert_not_called()
