"""The native screenshot handshake tolerates absent adb marker files."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import unittest

from mobile_build.validation.document_storage_tools import lockscreen_capture_name


class LockScreenProtocolTests(unittest.TestCase):
    def test_absent_or_incomplete_marker_is_pending(self):
        for raw in (b'', b'cat: cache/lockscreen-capture.json: No such file or directory\n', b'{"name":'):
            with self.subTest(raw=raw):
                self.assertIsNone(lockscreen_capture_name(raw))

    def test_valid_request_and_invalid_destination(self):
        self.assertEqual(lockscreen_capture_name(b'{"name":"0-portrait-keyboard"}'), '0-portrait-keyboard')
        for raw in (b'{"name":"../outside"}', b'{"name":"two words"}', b'{"name":12}', b'[]'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                lockscreen_capture_name(raw)


if __name__ == '__main__':
    unittest.main()
