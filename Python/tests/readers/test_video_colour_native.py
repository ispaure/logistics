"""Visible PQ/HLG pixels, float HDR output, captions and privacy on a native display."""
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from shiboken6 import isValid
from commonUtils.testing.stages import TestStage
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.selection import ResourceChoice

TEST_STAGE = TestStage.EXTENDED


class NativeColourTests(QtTestCase):
    def setUp(self):
        super().setUp()
        if qt.QApplication.platformName() != 'cocoa':
            self.skipTest('Requires the native Cocoa display backend')
        value = os.environ.get('LOGISTICS_TEST_MPV_LIBRARY')
        if not value or not Path(value).is_file():
            self.skipTest('Set LOGISTICS_TEST_MPV_LIBRARY to a verified prepared libmpv runtime')
        if not shutil.which('ffmpeg'):
            self.skipTest('Requires FFmpeg for luminance fixtures')
        self.library = Path(value)
        self.evidence = Path(__file__).resolve().parents[3] / 'test-results/desktop-hdr/acceptance'
        self.evidence.mkdir(parents=True, exist_ok=True)

    def make_player(self, root, path):
        from features.video.ui.player import VideoWindow
        from features.video.ui.mpv_backend import MPVPlayback
        with patch('commonUtils.filesystem.storage.cache_directory', return_value=root / 'state'):
            window = VideoWindow(ResourceChoice(LocalFiles(root), path.name), backend_factory=lambda owner: MPVPlayback(
                owner, interactive=False, library_path=self.library))
        window.audio.setMuted(True)
        for shortcut in window.findChildren(qt.QShortcut):
            shortcut.setEnabled(False)
        window.setAttribute(qt.Qt.WidgetAttribute.WA_ShowWithoutActivating)
        window.video.probe_samples = True
        window.show()
        self.addCleanup(lambda: window.close() if isValid(window) else None)
        self.wait_until(lambda: window.have_frame and window.player.position() > 100 and window.video.samples, timeout=20)
        return window

    def record(self, window, name):
        data = dict(red_bits=window.video.red_bits, output_headroom=window.video.output_headroom,
                    samples=window.video.samples, source=window.player.source_colour, output=window.player.output_colour,
                    position=window.player.position(), duration=window.player.duration())
        (self.evidence / (name + '.json')).write_text(json.dumps(data, indent=2))
        window.screen().grabWindow(int(window.winId())).save(str(self.evidence / (name + '.png')))

    def test_pq_and_hlg_have_visible_sdr_and_float_hdr_in_both_layouts(self):
        from logistics_build.build_retention import scratch
        from tests.readers.video_fixtures import luminance_movie
        from features.video.ui.mpv_surface import CocoaGL
        for transfer in ('pq', 'hlg'):
            with self.subTest(transfer=transfer), scratch() as root:
                path, _ = luminance_movie(root, transfer)
                window = self.make_player(root, path)
                try:
                    self.assertIn(window.player.source_colour.get('gamma'), {'pq', 'hlg'})
                    self.assertIn(window.player.source_colour.get('pixelformat'), {'p010', 'yuv420p10'})
                    self.assertEqual(window.video.red_bits, 16)
                    window.pause_requested()
                    window.change_setting('colour_output', 'sdr')
                    self.wait_until(lambda: window.video.samples and window.video.output_headroom == 1)
                    sdr = [sum(pixel[:3]) / 3 for pixel in window.video.samples]
                    self.assertTrue(all(b > a + .002 for a, b in zip(sdr, sdr[1:])), sdr)
                    self.assertLessEqual(max(sdr), 1.01)
                    self.record(window, transfer + '-windowed-sdr')
                    # Exercise the output range even on an SDR-only test screen.
                    # This proves the float pipeline, not physical HDR luminance.
                    with patch.object(CocoaGL, 'headroom', return_value=4.):
                        window.change_setting('colour_output', 'auto')
                        self.wait_until(lambda: window.video.output_headroom == 4 and
                                        max(pixel[0] for pixel in window.video.samples) > 1.1, timeout=10,
                                        message=lambda: str((window.video.output_headroom, window.video.samples, window.player.output_colour, window.backend.core.queue.qsize())))
                        self.record(window, transfer + '-windowed-hdr-range')
                        window.toggle_fullscreen()
                        self.wait_until(lambda: window.isFullScreen())
                        loop = qt.QEventLoop()
                        qt.QTimer.singleShot(600, loop.quit)
                        loop.exec()
                        self.assertGreater(max(pixel[0] for pixel in window.video.samples), 1.1)
                        self.record(window, transfer + '-fullscreen-hdr-range')
                        window.change_setting('colour_output', 'sdr')
                        self.wait_until(lambda: max(pixel[0] for pixel in window.video.samples) <= 1.01, timeout=10,
                                        message=lambda: str((window.video.output_headroom, window.video.samples, window.player.output_colour, window.backend.core.queue.qsize())))
                        self.record(window, transfer + '-fullscreen-sdr')
                    window.player.setPosition(1000)
                    self.wait_until(lambda: window.player._pending_seek is None and abs(window.player.position() - 1000) < 200)
                    self.assertEqual(window.player.playbackState(), window.player.PlaybackState.PausedState)
                    window.fullscreen.leave()
                finally:
                    window.close()
                    self.assertFalse(window.backend.core.thread.is_alive())

    def test_rendered_captions_and_credential_lock_clear_the_native_surface(self):
        from logistics_build.build_retention import scratch
        from tests.readers.video_fixtures import bundled_movie
        from features.video.ui.privacy import VideoResumeGuard
        with scratch() as root:
            path = bundled_movie('black.mkv', root)
            (root / 'caption.srt').write_text('1\n00:00:00,000 --> 00:00:11,000\nVISIBLE PRIVATE CAPTION\n')
            window = self.make_player(root, path)
            with patch('services.documents.ui.editors.choose_editor_resource', return_value=ResourceChoice(
                    window.content.provider, 'caption.srt')):
                window.load_subtitles()
            self.wait_until(lambda: any(row.get('external') and row.get('selected') for row in window.player._tracks), timeout=10)
            def white_pixels():
                image = window.video.capture().convertToFormat(qt.QImage.Format.Format_Grayscale8)
                return sum(value > 100 for value in bytes(image.constBits()))
            self.wait_until(lambda: white_pixels() > 30, timeout=10)
            self.record(window, 'caption')
            guard = VideoResumeGuard(window, authorization=SimpleNamespace(password_gate=None))
            window.resume_guard = guard
            old_generation = window.player.generation
            guard.lock()
            window.player.snapshot({"generation": old_generation, "loaded": True,
                                    "video-out-params": {"w": 320, "h": 180}, "time-pos": 9})
            self.wait_until(lambda: not window.video.have_frame and not window.video.source_ready)
            self.assertTrue(window.player.source().isEmpty())
            self.assertTrue(guard.blocked)
            self.assertFalse(window.requested_play)
            window.close()
            self.assertFalse(window.backend.core.thread.is_alive())

    def test_codec_matrix_and_renderer_handoff_preserve_pause_and_position(self):
        from logistics_build.build_retention import scratch
        from tests.readers.video_fixtures import codec_matrix
        from features.video.ui.player import VideoWindow
        from features.video.ui.vlc_backend import VLCPlayback
        with scratch() as root:
            for container, video, audio, path in codec_matrix(root):
                with self.subTest(container=container, video=video, audio=audio):
                    window = self.make_player(root, path)
                    try:
                        self.wait_until(lambda: bool(window.player._tracks))
                        self.assertTrue(window.player.audioTracks())
                        self.assertTrue(any(row.get('type') == 'audio' and row.get('selected')
                                            for row in window.player._tracks))
                        window.pause_requested()
                        window.player.setPosition(1000)
                        self.wait_until(lambda: window.player._pending_seek is None)
                        if container == 'mp4' and video == 'h264' and audio == 'aac':
                            retained = []
                            def retain(candidate):
                                retained.append(candidate)
                                candidate.audio.setMuted(True)
                                candidate.show()
                                return candidate
                            with patch('services.documents.ui.editors.retain', side_effect=retain):
                                window.reopen_renderer('compatibility')
                            self.assertEqual(len(retained), 1)
                            candidate = retained[0]
                            try:
                                self.assertIsInstance(candidate.backend, VLCPlayback)
                                self.wait_until(lambda: candidate.have_frame, timeout=20)
                                self.assertEqual(candidate.player.playbackState(), candidate.player.PlaybackState.PausedState)
                                self.assertLess(abs(candidate.player.position() - 1000), 250)
                                self.assertFalse(window.backend.core.thread.is_alive())
                            finally:
                                candidate.close()
                    finally:
                        if isValid(window):
                            window.close()

    def test_speed_changes_drive_the_native_media_clock(self):
        from logistics_build.build_retention import scratch
        from tests.readers.video_fixtures import bundled_movie
        from time import monotonic
        with scratch() as root:
            window = self.make_player(root, bundled_movie('speed-with-audio.mkv', root))
            try:
                for rate in (2., .5, 1.5):
                    window.pause_requested()
                    window.change_setting('rate', rate)
                    window.player.setPosition(1000)
                    self.wait_until(lambda: window.player._pending_seek is None)
                    window.toggle_play()
                    self.wait_until(lambda: window.player.position() > 1400)
                    start, before = monotonic(), window.player.position()
                    self.wait_until(lambda: monotonic() - start > 1)
                    measured = (window.player.position() - before) / ((monotonic() - start) * 1000)
                    self.assertLess(abs(measured - rate), .35, (rate, measured))
            finally:
                window.close()

    def test_end_of_media_can_restart_and_complete_again(self):
        from logistics_build.build_retention import scratch
        from tests.readers.video_fixtures import bundled_movie
        with scratch() as root:
            window = self.make_player(root, bundled_movie('h264-aac.mp4', root))
            try:
                self.wait_until(lambda: window.ended, timeout=8)
                self.assertFalse(window.requested_play)
                window.toggle_play()
                self.wait_until(lambda: not window.ended and 100 < window.player.position() < 1500)
                self.wait_until(lambda: window.ended, timeout=8)
                self.assertFalse(window.requested_play)
            finally:
                window.close()
