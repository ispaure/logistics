"""Workspaces retain host-specific palette and control placement."""
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import MagicMock, patch
from logisticsmobile import appearance


class WorkspaceSurfacesTests(TestCase):
    def test_ios_icon_refresh_and_repaint_keep_disclosure_space(self):
        from logisticsmobile.control_icons import button_icons
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
        from logisticsmobile.startup import StartupScreen
        screen = StartupScreen()
        labels = [screen.status, screen.detail, screen.view.children[0].children[0]]
        self.assertTrue(all(not label._impl._surface_eink_outlined for label in labels))
