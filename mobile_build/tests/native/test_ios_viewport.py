"""Native size and inset changes wake responsive layouts without navigation."""
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from mobile.ios_reader_chrome import notify_viewport


class ViewportTests(unittest.TestCase):
    def test_size_and_inset_changes_coalesce_and_wake_on_portrait_return(self):
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)
        app = SimpleNamespace(active_host=True, loop=loop, resize_workspace=Mock())
        container = SimpleNamespace(content=SimpleNamespace(interface=SimpleNamespace(app=app)),
                                    width=390, height=700, top_inset=100, bottom_inset=34,
                                    left_inset=0, right_inset=0)
        async def exercise():
            notify_viewport(container)
            notify_viewport(container)
            await asyncio.sleep(0)
            self.assertEqual(app.resize_workspace.call_count, 1)
            for width, height, left in ((740, 320, 59), (390, 700, 0), (390, 700, 4)):
                container.width, container.height, container.left_inset = width, height, left
                notify_viewport(container)
                await asyncio.sleep(0)
            self.assertEqual(app.resize_workspace.call_count, 4)
            container.width = 800
            notify_viewport(container)
            app.active_host = False
            await asyncio.sleep(0)
            self.assertEqual(app.resize_workspace.call_count, 4)
        loop.run_until_complete(exercise())


class AndroidViewportTests(unittest.TestCase):
    def test_unchanged_global_layout_does_not_reenter_responsive_panels(self):
        from mobile.layout_events import native_resize_changed
        backend = type('Backend', (), {'__module__': 'toga_android.app'})
        native = Mock()
        native.getWidth.return_value, native.getHeight.return_value = 1080, 1920
        for name in ('getPaddingLeft', 'getPaddingTop', 'getPaddingRight', 'getPaddingBottom'):
            getattr(native, name).return_value = 0
        bar = Mock()
        bar.getWidth.return_value, bar.getVisibility.return_value = 1080, 0
        window = object()
        app = SimpleNamespace(main_window=window, _impl=backend(), body=object(),
            native_host=SimpleNamespace(adapter=SimpleNamespace(mode='bottom',
                impl=SimpleNamespace(native=native, native_navigationview=bar)),
                state=SimpleNamespace(destination='files')))
        self.assertTrue(native_resize_changed(app, window))
        self.assertFalse(native_resize_changed(app, window))
        native.getPaddingBottom.return_value = 400
        self.assertTrue(native_resize_changed(app, window))
        self.assertFalse(native_resize_changed(app, window))
        self.assertTrue(native_resize_changed(app, None))
        app.native_host.state.destination = 'chat'
        self.assertTrue(native_resize_changed(app, window))


class FixedControlAuditTests(unittest.TestCase):
    def test_callable_native_window_is_counted_and_cutout_overlap_is_rejected(self):
        import toga
        from unittest.mock import patch
        from mobile_build.native_tests.tests.logisticsmobile import rotation_checks
        window = SimpleNamespace(ptr=SimpleNamespace(value=1),
            safeAreaInsets=SimpleNamespace(left=47, right=47, top=0, bottom=21),
            bounds=SimpleNamespace(size=SimpleNamespace(width=844, height=390)))
        rect = SimpleNamespace(origin=SimpleNamespace(x=47, y=20),
                               size=SimpleNamespace(width=100, height=44))
        button = toga.Button('Keep clear of the notch')
        body = toga.Box(children=[button])
        native = SimpleNamespace(window=lambda: window, isHidden=lambda: False,
                                 bounds=object(), convertRect=lambda *args, **kwargs: rect)
        app = SimpleNamespace(body=body, main_window=SimpleNamespace(_impl=SimpleNamespace(native=window)))
        with patch.object(rotation_checks.sys, 'platform', 'ios'), \
                patch.object(body._impl, 'native', SimpleNamespace(window=lambda: window), create=True), \
                patch.object(button._impl, 'native', native, create=True):
            self.assertEqual(rotation_checks.assert_visible_controls(app), 1)
            body.title_actions = (button,)
            self.assertEqual(rotation_checks.assert_visible_controls(app), 1)
            body.remove(button)
            self.assertEqual(rotation_checks.assert_visible_controls(app), 1)
            rect.origin.x = 0
            with self.assertRaises(AssertionError):
                rotation_checks.assert_visible_controls(app)

    def test_uikit_navigation_uses_bar_bounds_while_content_keeps_safe_insets(self):
        import toga
        import sys
        from unittest.mock import patch
        from mobile_build.native_tests.tests.logisticsmobile import rotation_checks
        window = SimpleNamespace(ptr=SimpleNamespace(value=1),
            safeAreaInsets=SimpleNamespace(left=62, right=62, top=0, bottom=20),
            bounds=SimpleNamespace(size=SimpleNamespace(width=874, height=402)))
        bounds = SimpleNamespace(origin=SimpleNamespace(x=0, y=0),
                                 size=SimpleNamespace(width=874, height=54))
        rect = SimpleNamespace(origin=SimpleNamespace(x=38, y=0),
                               size=SimpleNamespace(width=44, height=44))
        body = toga.Box()
        native = SimpleNamespace(window=lambda: window, isHidden=lambda: False, alpha=1,
            bounds=object(), convertRect=Mock(return_value=rect), accessibilityLabel=None,
            isKindOfClass=lambda cls: True, subviews=[])
        bar = SimpleNamespace(isHidden=lambda: False, alpha=1, window=lambda: window,
            accessibilityLabel=None, bounds=bounds,
            isKindOfClass=lambda cls: False, subviews=lambda: [native])
        host = SimpleNamespace(adapter=SimpleNamespace(navigation=[SimpleNamespace(navigationBar=lambda: bar)]),
            destinations=['files'], state=SimpleNamespace(destination='files'))
        app = SimpleNamespace(body=body, native_host=host,
            main_window=SimpleNamespace(_impl=SimpleNamespace(native=window)))
        with patch.object(rotation_checks.sys, 'platform', 'ios'), \
                patch.dict(sys.modules, {'rubicon.objc': SimpleNamespace(ObjCClass=lambda name: object())}), \
                patch.object(body._impl, 'native', SimpleNamespace(window=lambda: window), create=True):
            self.assertEqual(rotation_checks.assert_visible_controls(app), 1)
            native.convertRect.assert_called_with(native.bounds, toView=bar)
            with self.assertRaises(AssertionError):
                rotation_checks.assert_control_bounds(rect, window, 'Content control')
            rect.origin.x = -5
            with self.assertRaises(AssertionError):
                rotation_checks.assert_visible_controls(app)
