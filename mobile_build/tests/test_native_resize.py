"""Native child layout cannot recursively re-enter an unchanged Android viewport."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from mobile.layout_events import native_resize_changed


class NativeResizeTests(unittest.TestCase):
    def setUp(self):
        backend = type('Backend', (), {'__module__': 'toga_android.app'})
        native, bar = Mock(), Mock()
        native.getWidth.return_value, native.getHeight.return_value = 1080, 1920
        for name in ('getPaddingLeft', 'getPaddingTop', 'getPaddingRight', 'getPaddingBottom'):
            getattr(native, name).return_value = 0
        bar.getWidth.return_value, bar.getVisibility.return_value = 1080, 0
        self.native, self.bar = native, bar
        self.app = SimpleNamespace(main_window=object(), _impl=backend(), body=object(),
            native_host=SimpleNamespace(adapter=SimpleNamespace(mode='bottom',
                impl=SimpleNamespace(native=native, native_navigationview=bar)),
                state=SimpleNamespace(destination='files')))

    def test_geometry_keyboard_destination_and_content_changes_still_resize(self):
        app = self.app
        self.assertTrue(native_resize_changed(app, app.main_window))
        self.assertFalse(native_resize_changed(app, app.main_window))
        for change in (
            lambda: setattr(self.native.getPaddingBottom, 'return_value', 400),
            lambda: setattr(self.native.getHeight, 'return_value', 1080),
            lambda: setattr(self.bar.getVisibility, 'return_value', 8),
            lambda: setattr(app.native_host.state, 'destination', 'chat'),
            lambda: setattr(app, 'body', object()),
        ):
            change()
            self.assertTrue(native_resize_changed(app, app.main_window))
            self.assertFalse(native_resize_changed(app, app.main_window))
        self.assertTrue(native_resize_changed(app, None))

    def test_unchanged_native_callback_stops_before_reflowing_children(self):
        from mobile.app import LogisticsMobile
        app = self.app
        native_resize_changed(app, app.main_window)
        with patch('mobile.keyboard.fit_editors') as fit:
            LogisticsMobile.resize_workspace(app, app.main_window)
            fit.assert_not_called()
        self.native.getHeight.return_value = 1400
        with patch('mobile.keyboard.fit_editors', side_effect=RuntimeError('entered reflow')):
            with self.assertRaisesRegex(RuntimeError, 'entered reflow'):
                LogisticsMobile.resize_workspace(app, app.main_window)
