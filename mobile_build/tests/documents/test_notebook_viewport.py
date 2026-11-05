"""Native device identity keeps narrow iPad paper defaults distinct from phones."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from features.notebooks.mobile.viewport import tablet_viewport


def web(backend, native=None):
    implementation = type('WebView', (), {'__module__': backend})()
    implementation.native = native
    return SimpleNamespace(_impl=implementation)


class NotebookViewportTests(unittest.TestCase):
    def test_ipad_identity_does_not_depend_on_current_window_width(self):
        for idiom, tablet in ((1, True), (0, False)):
            device = SimpleNamespace(currentDevice=SimpleNamespace(userInterfaceIdiom=idiom))
            with patch.dict(sys.modules, {'rubicon.objc': SimpleNamespace(ObjCClass=lambda name: device)}):
                self.assertEqual(tablet_viewport(web('toga_iOS.widgets.webview')), tablet)

    def test_android_uses_native_smallest_screen_configuration(self):
        for width, tablet in ((599, False), (600, True), (840, True)):
            configuration = SimpleNamespace(smallestScreenWidthDp=width)
            resources = SimpleNamespace(getConfiguration=lambda: configuration)
            native = SimpleNamespace(getResources=lambda: resources)
            self.assertEqual(tablet_viewport(web('toga_android.widgets.webview', native)), tablet)

    def test_portable_and_unmounted_webviews_use_geometry_fallback(self):
        self.assertIsNone(tablet_viewport(None))
        self.assertIsNone(tablet_viewport(web('toga_dummy.widgets.webview')))

    def test_private_native_subclasses_keep_device_identity(self):
        for backend in ('toga_iOS.widgets.webview', 'toga_android.widgets.webview'):
            native = SimpleNamespace(getResources=lambda: SimpleNamespace(
                getConfiguration=lambda: SimpleNamespace(smallestScreenWidthDp=700)))
            ordinary = web(backend, native)
            secured = type('PrivateBackend', (type(ordinary._impl),),
                           {'__module__': 'commonUtils.ui.native.private_webview'})()
            secured.native = native
            device = SimpleNamespace(currentDevice=SimpleNamespace(userInterfaceIdiom=1))
            with self.subTest(backend=backend), patch.dict(sys.modules, {
                    'rubicon.objc': SimpleNamespace(ObjCClass=lambda name: device)}):
                self.assertTrue(tablet_viewport(SimpleNamespace(_impl=secured)))
