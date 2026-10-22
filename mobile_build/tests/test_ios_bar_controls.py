"""UIKit alone paints bar backgrounds, including after a surface refresh."""
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import Mock, patch

from mobile.appearance import paint_surface
from mobile.ios_reader_chrome import action_groups


class AppleBarControlTests(TestCase):
    def test_semantic_navigation_and_document_tools_share_separate_glass(self):
        buttons = [NS(control_icon=name) for name in ('previous_comic', 'next_comic', 'speaker', 'more')]
        self.assertEqual(action_groups(buttons), [buttons[:2], buttons[2:]])
        self.assertEqual(action_groups(buttons[1:]), [[buttons[1]], buttons[2:]])
        self.assertEqual(action_groups([]), [])

    def test_mount_and_trait_repaint_remove_inner_fill_without_losing_menu(self):
        impl_type = type('Button', (), {'__module__': 'toga_iOS.widgets.button'})
        impl = impl_type()
        impl.native = Mock()
        impl.interface = NS(on_press=Mock(), control_icon='close')
        impl._surface_roles = ('surface', 'text', True)
        impl._native_bar_control = True
        impl._native_glass_control = True  # Bar glass takes precedence over inline glass.
        menu = impl.native.menu
        with patch('mobile.appearance.apple_color', side_effect=lambda role: Mock(name=role)) as color, patch.dict(
                'sys.modules', {'rubicon.objc': NS(UIEdgeInsets=lambda *args: args)}):
            for radius in (0, 8):
                paint_surface(impl, radius)
                self.assertEqual(impl.native.backgroundColor._mock_name, 'transparent')
                self.assertEqual(impl.native.layer.borderWidth, 0)
                self.assertEqual(impl.native.layer.cornerRadius, 0)
                self.assertIsNone(impl.native.configuration)
                self.assertIs(impl.native.menu, menu)
            self.assertNotIn('surface', [call.args[0] for call in color.call_args_list])

    def test_standalone_glass_survives_refresh_and_uses_older_system_fallback(self):
        impl = type('Button', (), {'__module__': 'toga_iOS.widgets.button'})()
        impl.native, impl.interface = Mock(), NS(on_press=Mock(), control_icon=None)
        impl._surface_roles = ('surface', 'text', False)
        impl._native_glass_control = True
        configuration = Mock()
        config = Mock()
        configuration.glassButtonConfiguration.return_value = config
        configuration.grayButtonConfiguration.return_value = config
        objc = NS(ObjCClass=lambda name: configuration, SEL=lambda value: value, UIEdgeInsets=lambda *args: args)
        with patch.dict('sys.modules', {'rubicon.objc': objc}), patch(
                'mobile.appearance.apple_color', side_effect=lambda role: Mock(name=role)):
            for modern in (True, False):
                configuration.respondsToSelector.return_value = modern
                paint_surface(impl, 8)
                self.assertIs(impl.native.configuration, config)
                self.assertEqual(impl.native.backgroundColor._mock_name, 'transparent')
                self.assertEqual(config.cornerStyle, 4)
        configuration.glassButtonConfiguration.assert_called_once()
        configuration.grayButtonConfiguration.assert_called_once()
