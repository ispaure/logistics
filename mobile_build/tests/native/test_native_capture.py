"""Screenshots copy the composited window and release encoding resources."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from commonUtils.runtime.platform import OS

from mobile_build.native_tests.tests.logisticsmobile import fixtures


class NativeCaptureTests(unittest.IsolatedAsyncioTestCase):
    def capture_fixture(self, result=0):
        png = b'\x89PNG' + bytes(range(128))
        calls = []
        output = SimpleNamespace(toByteArray=lambda: png, close=lambda: calls.append('closed'))
        def compress(*args):
            self.assertIn('copied', calls)
            calls.append('compressed')
            return True
        bitmap = SimpleNamespace(compress=compress, recycle=lambda: calls.append('recycled'))
        def create(width, height, config):
            self.assertEqual((width, height), (640, 480))
            return bitmap
        decor = SimpleNamespace(getWidth=lambda: 640, getHeight=lambda: 480,
                                draw=lambda canvas: self.fail('Software capture omits accelerated ink'))
        window = SimpleNamespace(getDecorView=lambda: decor)
        handler = object()
        def copy(native_window, target, listener, callback_handler):
            self.assertIs(native_window, window)
            self.assertIs(target, bitmap)
            self.assertIs(callback_handler, handler)
            calls.append('request')
            def completed():
                calls.append('copied')
                listener.onPixelCopyFinished(result)
            asyncio.get_running_loop().call_soon(completed)
        classes = {'android.graphics.Bitmap': SimpleNamespace(createBitmap=create),
                   'android.graphics.Bitmap$Config': SimpleNamespace(ARGB_8888=object()),
                   'android.graphics.Bitmap$CompressFormat': SimpleNamespace(PNG=object()),
                   'android.view.PixelCopy': SimpleNamespace(SUCCESS=0, request=copy),
                   'android.view.PixelCopy$OnPixelCopyFinishedListener': object,
                   'android.os.Handler': lambda looper: handler,
                   'android.os.Looper': SimpleNamespace(getMainLooper=lambda: object()),
                   'java.io.ByteArrayOutputStream': lambda: output}
        app = SimpleNamespace(_impl=SimpleNamespace(native=SimpleNamespace(
            getWindow=lambda: window)))
        return app, SimpleNamespace(jclass=classes.__getitem__, dynamic_proxy=lambda interface: object), calls, png

    async def test_reparented_content_does_not_control_window_capture(self):
        app, java, calls, png = self.capture_fixture()
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'window.png'
            with patch('commonUtils.runtime.platform.get_os', return_value=OS.ANDROID), \
                    patch.dict('sys.modules', java=java):
                await fixtures.capture_window(app, path)
            self.assertEqual(path.read_bytes(), png)
        self.assertEqual(calls, ['request', 'copied', 'compressed', 'closed', 'recycled'])

    async def test_pixelcopy_failure_releases_resources_without_publishing_screenshot(self):
        app, java, calls, _ = self.capture_fixture(result=1)
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'window.png'
            with patch('commonUtils.runtime.platform.get_os', return_value=OS.ANDROID), \
                    patch.dict('sys.modules', java=java):
                with self.assertRaisesRegex(OSError, 'PixelCopy 1'):
                    await fixtures.capture_window(app, path)
            self.assertFalse(path.exists())
        self.assertEqual(calls, ['request', 'copied', 'closed', 'recycled'])
