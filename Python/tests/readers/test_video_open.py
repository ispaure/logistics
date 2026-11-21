"""Exercise the desktop document open path against the production VLC decoder."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from contextlib import contextmanager
from threading import Event, Timer
from unittest.mock import Mock, patch

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.selection import ResourceChoice
from commonUtils.testing.stages import TestStage
from commonUtils.tests.qt_test_case import QtTestCase
from features.video.ui.backend import OPEN_ERROR, VIDEO_TRACK_ERROR
from features.video.ui.player import VideoWindow
from logistics_build.build_retention import scratch
from tests.readers.decoder_fixtures import headless_vlc_playback
from tests.readers.video_fixtures import bundled_movie

TEST_STAGE = TestStage.REGRESSION


class VideoOpenTests(QtTestCase):
    @contextmanager
    def video(self, root, name):
        release = Mock()
        choice = ResourceChoice(LocalFiles(root), name, release)
        with patch('commonUtils.filesystem.storage.cache_directory', return_value=root / 'cache'):
            window = VideoWindow(choice, backend_factory=headless_vlc_playback)
        try:
            yield window
        finally:
            window.close()
            self.wait_until(lambda: release.called, drain_deferred=True)
            release.assert_called_once()
            self.assertTrue(window.content.closed)

    def test_empty_native_end_reports_failed_open_and_supported_replacement_plays(self):
        with scratch() as root:
            movie = bundled_movie('mpeg4-mp3.avi', root)
            data = movie.read_bytes()
            self.assertGreaterEqual(data.count(b'FMP4'), 2)
            cases = {
                'unknown-codec.avi': (data.replace(b'FMP4', b'ZZZZ', 2), VIDEO_TRACK_ERROR),
                'truncated.avi': (data[:24], OPEN_ERROR),
                'unrecognized.avi': (b'Synthetic bytes with no media header', OPEN_ERROR),
            }
            for name, (fixture, message) in cases.items():
                with self.subTest(name=name):
                    (root / name).write_bytes(fixture)
                    with self.video(root, name) as window:
                        self.wait_until(lambda: window.status.text() == message,
                                        message=lambda: window.status.text())
                        self.assertFalse(window.ended)
                        self.assertFalse(window.requested_play)
                    with self.video(root, movie.name) as replacement:
                        self.wait_until(lambda: replacement.have_frame
                                        and replacement.player.stats.played_abuffers > 0)

    def test_video_and_audio_play_without_a_declared_duration(self):
        with scratch() as root:
            stream = bundled_movie('unknown-duration.mkv', root)
            with self.video(root, stream.name) as window:
                self.wait_until(lambda: window.have_frame and window.player.stats.played_abuffers > 0)
                self.assertEqual(window.player.duration(), 0)
                self.assertIn('Duration unknown', window.time.text())
                self.assertFalse(window.seek.isEnabled())

    def test_provider_timeout_is_retryable_and_not_a_decode_failure(self):
        with scratch() as root:
            movie = bundled_movie('mjpeg-pcm.avi', root)
            with self.video(root, movie.name) as window:
                open_content = window.content.open
                available = Event()

                @contextmanager
                def open_range():
                    if not available.is_set():
                        raise TimeoutError('Synthetic provider timeout')
                    with open_content() as stream:
                        yield stream

                with patch.object(window.content, 'open', open_range):
                    self.wait_until(lambda: 'Check the connection' in window.status.text())
                    self.assertFalse(window.ended)
                    self.assertFalse(window.requested_play)
                    available.set()
                    window.play.click()
                    self.wait_until(lambda: window.have_frame and window.player.stats.played_abuffers > 0)

    def test_delayed_provider_open_recovers_without_a_second_play_request(self):
        with scratch() as root:
            movie = bundled_movie('mpeg4-mp3.avi', root)
            with self.video(root, movie.name) as window:
                open_content = window.content.open
                available, entered = Event(), Event()
                release = Timer(.8, available.set)

                @contextmanager
                def open_range():
                    entered.set()
                    if not available.wait(4):
                        raise TimeoutError('Synthetic provider timeout')
                    with open_content() as stream:
                        yield stream

                with patch.object(window.content, 'open', open_range):
                    release.start()
                    try:
                        self.wait_until(lambda: entered.is_set())
                        self.assertTrue(window.requested_play)
                        self.wait_until(lambda: window.have_frame and window.player.stats.played_abuffers > 0)
                    finally:
                        available.set()
                        release.cancel()
                        release.join()

    def test_startup_deadline_and_user_pause_stop_play_intent(self):
        with scratch() as root:
            movie = bundled_movie('mpeg4-mp3.avi', root)
            for pause in (False, True):
                with self.subTest(pause=pause), self.video(root, movie.name) as window:
                    open_content = window.content.open
                    entered, release = Event(), Event()

                    @contextmanager
                    def open_range():
                        entered.set()
                        if not release.wait(4):
                            raise TimeoutError('Synthetic provider timeout')
                        with open_content() as stream:
                            yield stream

                    with patch.object(window.content, 'open', open_range), patch(
                            'features.video.ui.player.OPEN_TIMEOUT', 2 if pause else .1):
                        try:
                            self.wait_until(lambda: entered.is_set())
                            if pause:
                                window.play.click()
                                self.assertEqual(window.status.text(), 'Paused.')
                            else:
                                self.wait_until(lambda: 'did not start in time' in window.status.text())
                            self.assertFalse(window.requested_play)
                            self.assertIsNone(window.open_deadline)
                        finally:
                            release.set()
