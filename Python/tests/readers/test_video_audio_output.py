"""Native audio ownership and lifetime on every desktop, without FFmpeg tools."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.video.ui.audio_output import audio_output
from PySide6.QtMultimedia import QAudioOutput
from PySide6.QtQml import QQmlEngine
import shiboken6


class NativeAudioOutputTests(QtTestCase):
    def test_native_callbacks_controls_and_window_owned_engine_retire_together(self):
        for cycle in range(8):
            with self.subTest(cycle=cycle):
                window = qt.QWidget()
                output = audio_output(window)
                self.assertIsInstance(output, QAudioOutput)
                self.assertFalse(shiboken6.createdByPython(output))
                self.assertIs(output.parent(), window)
                engines = output.findChildren(QQmlEngine)
                self.assertEqual(len(engines), 1)
                output.setVolume(.35)
                output.setMuted(True)
                self.assertAlmostEqual(output.volume(), .35, places=5)
                self.assertTrue(output.isMuted())
                output.setMuted(False)
                self.assertFalse(output.isMuted())
                window.deleteLater()
                self.wait_until(lambda: not shiboken6.isValid(window), drain_deferred=True)
                self.assertFalse(shiboken6.isValid(output))
                self.assertFalse(shiboken6.isValid(engines[0]))
