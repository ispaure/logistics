"""Decode real frames/audio for every requested desktop container/codec pairing."""

from commonUtils.testing.stages import TestStage, stage

TEST_STAGE = TestStage.EXTENDED
from pathlib import Path
import shutil
import unittest
from unittest.mock import Mock, patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.selection import ResourceChoice


class VideoDecodeTests(QtTestCase):
    def test_playback_buttons_and_narrow_layout(self):
        from logistics_build.build_retention import scratch
        from tests.readers.video_fixtures import bundled_movie
        from features.video.ui.player import VideoWindow
        from PySide6.QtMultimedia import QMediaPlayer
        with scratch() as root:
            path = bundled_movie('h264-aac.mp4', root)
            release = Mock()
            with patch('commonUtils.filesystem.storage.cache_directory', return_value=root / 'cache'):
                window = VideoWindow(ResourceChoice(LocalFiles(root), path.name, release))
            try:
                window.show()
                self.wait_until(lambda: window.player.duration() > 1000
                    and window.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
                    and window.player.position() > 100)
                window.play.click()
                self.wait_until(lambda: window.player.playbackState() == QMediaPlayer.PlaybackState.PausedState)
                window.player.setPosition(1000)
                window.backward.click()
                self.assertEqual(window.player.position(), 0)
                window.forward.click()
                self.assertLessEqual(window.player.position(), window.player.duration())
                self.assertFalse(window.undo_button.isVisible())  # The whole clip is shorter than a large seek.
                window.mute.click()
                self.assertTrue(window.audio.isMuted())
                self.assertEqual(window.mute.accessibleName(), 'Unmute')
                window.mute.click()
                self.assertFalse(window.audio.isMuted())
                window.update_play(QMediaPlayer.PlaybackState.PlayingState)
                self.assertEqual(window.play.accessibleName(), 'Pause')
                window.update_play(QMediaPlayer.PlaybackState.PausedState)
                output = Path(__file__).resolve().parents[3] / 'test-results/video-ui-desktop'
                output.mkdir(parents=True, exist_ok=True)
                for width, height in ((360, 640), (560, 420), (1000, 720)):
                    window.resize(width, height)
                    qt.QApplication.processEvents()
                    self.assertLessEqual(window.width(), width)
                    for button in (*window.action_buttons, window.play, window.backward, window.forward, window.mute):
                        self.assertTrue(button.isVisible())
                        point = button.mapTo(window, qt.QPoint(0, 0))
                        self.assertGreaterEqual(point.x(), 0)
                        self.assertLessEqual(point.x() + button.width(), window.width())
                        self.assertLessEqual(point.y() + button.height(), window.height())
                        timeline = window.seek.mapTo(window, qt.QPoint(0, 0))
                        self.assertLessEqual(timeline.y() + window.seek.height(), point.y())
                    window.grab().save(str(output / f'{width}x{height}.png'))
                window.fullscreen_button.click()
                self.assertTrue(window.isFullScreen())
                self.assertTrue(window.fullscreen_action.isChecked())
                window.fullscreen_button.click()
                self.assertFalse(window.isFullScreen())
                self.assertFalse(window.fullscreen_action.isChecked())
            finally:
                window.close()
                self.wait_until(lambda: release.called, drain_deferred=True)
                release.assert_called_once()
                self.assertTrue(window.content.closed)

    def test_embedded_chapter_panel_seeks_without_resuming_pause(self):
        from logistics_build.build_retention import scratch
        from tests.readers.video_fixtures import chapter_movie
        from features.video.ui.player import VideoWindow
        from PySide6.QtMultimedia import QMediaPlayer
        with scratch() as root:
            path = chapter_movie(root)
            release = Mock()
            with patch('commonUtils.filesystem.storage.cache_directory', return_value=root / 'cache'):
                window = VideoWindow(ResourceChoice(LocalFiles(root), path.name, release))
            try:
                self.wait_until(lambda: window.player.duration() > 10000 and window.player.position() > 100)
                window.player.pause()
                window.chapters.click()
                self.wait_until(lambda: window.chapter_data is not None)
                self.assertEqual([row.title for row in window.chapter_data], ['Opening', 'Second scene'])
                self.assertEqual(window.panel_name, 'chapters')
                buttons = window.settings_scroll.widget().findChildren(qt.QPushButton)
                buttons[1].click()
                self.wait_until(lambda: window.player.position() >= 5900)
                self.assertEqual(window.player.playbackState(), QMediaPlayer.PlaybackState.PausedState)
            finally:
                window.close()
                self.wait_until(lambda: release.called, drain_deferred=True)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg track muxer is required')
    def test_embedded_track_selection_and_external_srt(self):
        from logistics_build.build_retention import scratch
        from tests.readers.video_fixtures import bundled_movie, multitrack_movie
        from features.video.ui.player import VideoWindow
        with scratch() as root:
            path = multitrack_movie(root, bundled_movie('h264-aac.mp4', root))
            provider = LocalFiles(root)
            release = Mock()
            with patch('commonUtils.filesystem.storage.cache_directory', return_value=root / 'cache'):
                window = VideoWindow(ResourceChoice(provider, path.name, release))
            captions = []
            window.video.videoSink().videoFrameChanged.connect(
                lambda frame: captions.append(frame.subtitleText()) if frame.isValid() and frame.subtitleText() else None,
                qt.Qt.ConnectionType.QueuedConnection)
            try:
                window.toggle_play()
                self.wait_until(lambda: len(window.player.audioTracks()) == 2 and len(window.player.subtitleTracks()) == 1)
                window.player.setActiveAudioTrack(1)
                self.assertEqual(window.player.activeAudioTrack(), 1)
                window.select_subtitle(window.subtitle_tracks.findData(0))
                window.player.setPosition(100)
                self.wait_until(lambda: any('Embedded fixture caption' in text for text in captions), timeout=8)
                window.player.pause()
                choice = ResourceChoice(provider, 'tracks.srt', Mock())
                with patch('services.documents.ui.editors.choose_editor_resource', return_value=choice):
                    window.load_subtitles()
                window.position_changed(1000)
                self.assertEqual(window.caption.text(), 'Embedded fixture caption')
                self.assertTrue(window.external)
                window.select_subtitle(window.subtitle_tracks.findData(-1))
                self.assertEqual(window.caption.text(), '')
                self.assertEqual(window.player.activeSubtitleTrack(), -1)
            finally:
                window.close()
                self.wait_until(lambda: release.called, drain_deferred=True)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg track muxer is required')
    def test_repeated_track_changes_retire_native_audio_without_python_callbacks(self):
        import shiboken6
        from logistics_build.build_retention import scratch
        from tests.readers.video_fixtures import bundled_movie, multitrack_movie
        from features.video.ui.player import VideoWindow
        with scratch() as root:
            path = multitrack_movie(root, bundled_movie('h264-aac.mp4', root))
            for cycle in range(8):
                with self.subTest(cycle=cycle):
                    release = Mock()
                    with patch('commonUtils.filesystem.storage.cache_directory', return_value=root / 'cache'):
                        window = VideoWindow(ResourceChoice(LocalFiles(root), path.name, release))
                    audio = window.audio
                    try:
                        # A Python-created wrapper overrides disconnectNotify
                        # on the audio worker and can deadlock the track setter.
                        self.assertFalse(shiboken6.createdByPython(audio))
                        self.wait_until(lambda: len(window.player.audioTracks()) == 2
                                        and len(window.player.subtitleTracks()) == 1)
                        audio.setVolume(.35)
                        audio.setMuted(True)
                        for track in (1, 0, 1, 0):
                            window.player.setActiveAudioTrack(track)
                            window.select_subtitle(window.subtitle_tracks.findData(0))
                            self.wait_until(lambda: window.player.activeAudioTrack() == track
                                            and window.player.activeSubtitleTrack() == 0)
                            window.select_subtitle(window.subtitle_tracks.findData(-1))
                            self.assertEqual(window.player.activeSubtitleTrack(), -1)
                            self.assertAlmostEqual(audio.volume(), .35, places=5)
                            self.assertTrue(audio.isMuted())
                    finally:
                        window.close()
                        self.wait_until(lambda: release.called, drain_deferred=True)
                    self.assertFalse(shiboken6.isValid(audio))

    def test_requested_codec_matrix_decodes_video_and_audio(self):
        from PySide6.QtMultimedia import QAudioBufferOutput, QMediaPlayer, QVideoSink
        from logistics_build.build_retention import scratch
        from tests.readers.video_fixtures import codec_matrix
        from features.video.playback import VideoContent
        from features.video.transport import VideoTransport
        with scratch() as directory:
            for container, video, audio, path in codec_matrix(directory):
                with self.subTest(container=container, video=video, audio=audio):
                    content = VideoContent(LocalFiles(path.parent), path.name)
                    transport = VideoTransport(content)
                    player = QMediaPlayer()
                    sink, output = QVideoSink(player), QAudioBufferOutput(player)
                    player.setVideoSink(sink)
                    player.setAudioBufferOutput(output)
                    frames, samples, errors = [], [], []
                    sink.videoFrameChanged.connect(lambda frame, frames=frames: frames.append(frame.startTime()) if frame.isValid() else None)
                    output.audioBufferReceived.connect(lambda buffer, samples=samples: samples.append(buffer.frameCount()) if buffer.isValid() else None)
                    player.errorOccurred.connect(lambda error, message, errors=errors: errors.append(message))
                    try:
                        player.setSource(qt.QUrl(transport.url))
                        player.play()
                        self.wait_until(lambda: (frames and samples) or errors, timeout=12)
                        self.assertFalse(errors, errors)
                        self.assertTrue(frames, 'No decoded video frames')
                        self.assertTrue(samples, 'No decoded audio samples')
                        self.assertTrue(player.isSeekable())
                        player.pause()
                        player.setPosition(1000)
                        self.assertEqual(player.position(), 1000)
                    finally:
                        player.stop()
                        player.setSource(qt.QUrl())
                        transport.close()
                        content.close()
                        player.deleteLater()

    @stage(TestStage.REGRESSION)
    def test_transport_start_failure_releases_document_and_partial_window(self):
        from features.video.ui.player import open_video_choice
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / 'movie.mp4').write_bytes(b'fixture')
            release = Mock()
            choice = ResourceChoice(LocalFiles(root), 'movie.mp4', release)
            with patch('features.video.ui.player.VideoTransport', side_effect=PermissionError('Loopback unavailable')):
                with self.assertRaisesRegex(PermissionError, 'Loopback unavailable'):
                    open_video_choice(choice)
            self.assertTrue(release.called)
