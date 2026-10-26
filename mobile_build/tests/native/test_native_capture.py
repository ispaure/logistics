"""Screenshots use the native decor view and release encoding resources."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from commonUtils.runtime.platform import OS

from mobile_build.native_tests.tests.logisticsmobile import fixtures


class NativeCaptureTests(unittest.IsolatedAsyncioTestCase):
    async def test_reparented_content_does_not_control_window_capture(self):
        png = b'\x89PNG' + bytes(range(128))
        calls = []
        output = SimpleNamespace(toByteArray=lambda: png, close=lambda: calls.append('closed'))
        bitmap = SimpleNamespace(compress=lambda *args: True, recycle=lambda: calls.append('recycled'))
        def create(width, height, config):
            self.assertEqual((width, height), (640, 480))
            return bitmap
        classes = {'android.graphics.Bitmap': SimpleNamespace(createBitmap=create),
                   'android.graphics.Bitmap$Config': SimpleNamespace(ARGB_8888=object()),
                   'android.graphics.Bitmap$CompressFormat': SimpleNamespace(PNG=object()),
                   'android.graphics.Canvas': lambda bitmap: object(),
                   'java.io.ByteArrayOutputStream': lambda: output}
        decor = SimpleNamespace(getWidth=lambda: 640, getHeight=lambda: 480, draw=lambda canvas: calls.append('draw'))
        app = SimpleNamespace(_impl=SimpleNamespace(native=SimpleNamespace(
            getWindow=lambda: SimpleNamespace(getDecorView=lambda: decor))))
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'window.png'
            with patch('commonUtils.runtime.platform.get_os', return_value=OS.ANDROID), \
                    patch.dict('sys.modules', java=SimpleNamespace(jclass=classes.__getitem__)):
                await fixtures.capture_window(app, path)
            self.assertEqual(path.read_bytes(), png)
        self.assertEqual(calls, ['draw', 'closed', 'recycled'])
