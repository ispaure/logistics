"""Visible PQ/HLG pixels, float HDR output, captions and privacy on a native display."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import json
import os
from pathlib import Path
import shutil
import subprocess
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

    def test_subtitle_brightness_changes_only_current_cue(self):
        from features.video.ui.mpv_surface import CocoaGL
        from logistics_build.build_retention import scratch

        evidence = Path(__file__).resolve().parents[3] / 'tmp/test-results' / os.environ.get(
            'LOGISTICS_SUBTITLE_EVIDENCE', 'desktop-subtitle-brightness')
        evidence.mkdir(parents=True, exist_ok=True)
        receipt = {}
        with scratch() as root, patch.object(CocoaGL, 'headroom', return_value=4.):
            for hdr in (True, False):
                kind = 'pq' if hdr else 'sdr'
                path = root / f'{kind}.mkv'
                srt = root / 'caption.srt'
                srt.write_text('1\n00:00:00,000 --> 00:00:16,000\nSUBTITLE BRIGHTNESS\n')
                alternate = root / 'alternate.srt'
                alternate.write_text('1\n00:00:00,000 --> 00:00:16,000\nSECOND TRACK\n')
                luma = 'if(lt(N,96),327,609)' if hdr else 'if(lt(N,96),32,170)'
                neutral = 512 if hdr else 128
                codec = ['-c:v', 'libx264', '-colorspace', 'bt709', '-color_trc', 'bt709',
                         '-color_primaries', 'bt709']
                if hdr:
                    codec = ['-c:v', 'libx265', '-x265-params',
                             'pools=1:frame-threads=1:log-level=error:keyint=12:colorprim=9:transfer=16:colormatrix=9',
                             '-colorspace', 'bt2020nc', '-color_trc', 'smpte2084',
                             '-color_primaries', 'bt2020']
                subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                                f"nullsrc=s=320x180:r=12:d=16,format={'yuv420p10le' if hdr else 'yuv420p'},"
                                f"geq=lum='{luma}':cb={neutral}:cr={neutral}",
                                '-i', str(srt), '-i', str(alternate), '-map', '0:v', '-map', '1:s',
                                '-map', '2:s', '-threads', '1', *codec, '-c:s', 'srt', str(path)],
                               check=True, capture_output=True, timeout=45)
                window = self.make_player(root, path)
                try:
                    capture = window.video.sample_pixels
                    image = None
                    frames = 0
                    def capture_on_paint(width, height):
                        nonlocal image, frames
                        frames += 1
                        image = window.video.capture().convertToFormat(qt.QImage.Format.Format_RGBA8888)
                        return capture(width, height)
                    window.video.sample_pixels = capture_on_paint
                    window.show_settings('subtitles')
                    box = next(box for box in window.settings_pane.findChildren(qt.QComboBox)
                               if box.accessibleName() == 'Subtitle brightness')
                    window.change_setting('subtitle_track', 0)
                    for scene, target in [('dark', 1500), ('light', 9500)]:
                        window.player.setPosition(target)
                        self.wait_until(lambda: window.player._pending_seek is None and
                                        abs(window.player.position() - target) < 200, timeout=10)
                        self.wait_until(lambda: (window.video.samples[4][0] > .4) == (scene == 'light'),
                                        timeout=10)
                        snapshots, arrays, colours = {}, {}, {}
                        for level in ('dim', 'default', 'bright'):
                            expected = {'dim': 126, 'default': 138 if hdr else 148, 'bright': 148}[level]
                            box.setCurrentIndex(box.findData(level))
                            box.activated.emit(box.currentIndex())
                            # Wait for the rendered cue rather than assuming the
                            # asynchronous command has reached a display frame.
                            def cue_present():
                                if image is None:
                                    return False
                                red = bytes(image.constBits())[0::4]
                                return sum(red.count(code) for code in range(expected - 1, expected + 2)) > 200
                            self.wait_until(cue_present, timeout=1.5,
                                            message=lambda: str((kind, scene, level, frames)))
                            image.save(str(evidence / f'{kind}-{scene}-{level}.png'))
                            arrays[level] = bytes(image.constBits())[0::4]
                            snapshots[level] = window.video.samples
                            colours[level] = (window.player._subtitle_colour, frames)
                        self.assertEqual(window.player.activeSubtitleTrack(), 0)
                        self.assertGreaterEqual(window.player.position(), target - 200)
                        self.assertLess(window.player.position(), target + 5000)
                        self.assertEqual(window.player.playbackState(), window.player.PlaybackState.PlayingState)
                        dim, default, bright = (arrays[level] for level in ('dim', 'default', 'bright'))
                        largest = max(b - d for d, b in zip(dim, bright))
                        self.assertGreater(largest, 8, (kind, scene, window.player.source_colour,
                            colours, [max(array) for array in arrays.values()]))
                        glyph = [i for i, (d, b) in enumerate(zip(dim, bright)) if b - d >= largest - 2]
                        averages = [round(sum(sample[i] for i in glyph) / len(glyph), 2)
                                    for sample in (dim, default, bright)]
                        self.assertLess(averages[0], averages[1])
                        if hdr:
                            self.assertLess(averages[1], averages[2], (window.player.source_colour, colours, averages))
                        else:
                            self.assertEqual(default, bright)
                        self.assertEqual(snapshots['dim'], snapshots['default'])
                        self.assertEqual(snapshots['default'], snapshots['bright'])
                        self.assertEqual(dim[:image.width() * image.height() // 2],
                                         bright[:image.width() * image.height() // 2])
                        receipt[f'{kind}-{scene}'] = dict(
                            caption_red=averages, sampled_video=snapshots['default'],
                            source=window.player.source_colour, output_headroom=window.video.output_headroom)
                    window.change_setting('subtitle_track', 1)
                    self.wait_until(lambda: window.player.activeSubtitleTrack() == 1)
                    self.assertEqual(window.settings.subtitle_brightness, 'bright')
                    window.change_setting('subtitle_track', -1)
                    self.wait_until(lambda: window.player.activeSubtitleTrack() == -1)
                    window.change_setting('subtitle_track', 0)
                    self.wait_until(lambda: window.player.activeSubtitleTrack() == 0)
                finally:
                    window.close()
        (evidence / 'measurements.json').write_text(json.dumps(receipt, indent=2) + '\n')

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
