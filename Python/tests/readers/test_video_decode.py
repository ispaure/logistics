"""Decode real frames/audio for every requested desktop container/codec pairing."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.EXTENDED
from pathlib import Path
import shutil
import unittest
from unittest.mock import Mock, patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.selection import ResourceChoice


@unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg fixture generator is required')
class VideoDecodeTests(QtTestCase):
    def test_playback_buttons_and_narrow_layout(self):
        from logistics_build.build_retention import scratch
        from tests.readers.video_fixtures import codec_matrix
        from features.video.ui.player import VideoWindow
        from PySide6.QtMultimedia import QMediaPlayer
        with scratch() as root:
            path = codec_matrix(root)[0][3]
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
                        self.assertGreaterEqual(timeline.y(), point.y() + button.height())
                    window.grab().save(str(output / f'{width}x{height}.png'))
                window.fullscreen_button.click()
                self.assertTrue(window.isFullScreen())
                self.assertTrue(window.fullscreen_action.isChecked())
                window.fullscreen_button.click()
                self.assertFalse(window.isFullScreen())
                self.assertFalse(window.fullscreen_action.isChecked())
                window.floating.click()
                self.assertTrue(window.floating.isChecked())
                self.assertTrue(window.windowFlags() & qt.Qt.WindowType.WindowStaysOnTopHint)
                window.floating.click()
                self.assertFalse(window.floating.isChecked())
                self.assertFalse(window.windowFlags() & qt.Qt.WindowType.WindowStaysOnTopHint)
            finally:
                window.close()
                self.wait_until(lambda: release.called, drain_deferred=True)

    def test_embedded_chapter_menu_seeks_without_resuming_pause(self):
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
                self.assertIsNotNone(window.chapter_menu)
                window.chapter_menu.actions()[1].trigger()
                self.wait_until(lambda: window.player.position() >= 5900)
                self.assertEqual(window.player.playbackState(), QMediaPlayer.PlaybackState.PausedState)
            finally:
                window.close()
                self.wait_until(lambda: release.called, drain_deferred=True)

    def test_embedded_track_selection_and_external_srt(self):
        from logistics_build.build_retention import scratch
        from tests.readers.video_fixtures import codec_matrix, multitrack_movie
        from features.video.ui.player import VideoWindow
        with scratch() as root:
            fixtures = codec_matrix(root)
            path = multitrack_movie(root, fixtures[0][3])
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
                    sink, output = QVideoSink(), QAudioBufferOutput()
                    player.setVideoSink(sink)
                    player.setAudioBufferOutput(output)
                    frames, samples, errors = [], [], []
                    sink.videoFrameChanged.connect(lambda frame: frames.append(frame.startTime()) if frame.isValid() else None)
                    output.audioBufferReceived.connect(lambda buffer: samples.append(buffer.frameCount()) if buffer.isValid() else None)
                    player.errorOccurred.connect(lambda error, message: errors.append(message))
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

    def test_window_controls_and_restricted_floating_action(self):
        from features.video.ui.player import VideoWindow
        with self.temporary_directory() as directory:
            root = Path(directory)
            path = root / 'movie.mp4'
            path.write_bytes(b'not a decoded movie')
            provider = LocalFiles(root)
            provider.session_only = True
            release = Mock()
            choice = ResourceChoice(provider, path.name, release)
            with patch('commonUtils.filesystem.storage.cache_directory', return_value=root / 'cache'):
                window = VideoWindow(choice)
            self.assertFalse(window.floating.isEnabled())
            window.toggle_floating()
            self.assertIn('session-only', window.status.text())
            window.toggle_fullscreen()
            self.assertTrue(window.isFullScreen())
            window.toggle_fullscreen()
            self.assertFalse(window.isFullScreen())
            window.close()
            self.wait_until(lambda: release.called, drain_deferred=True)
            self.assertTrue(window.content.closed)

    def test_rclone_plain_and_crypt_cloud_streams_decode_frames_and_audio(self):
        from PySide6.QtMultimedia import QAudioBufferOutput, QMediaPlayer, QVideoSink
        from logistics_build.build_retention import scratch
        from tests.readers.video_fixtures import codec_matrix
        from tests.local_crypt_fixture import crypt_fixture
        from features.rclone import executable, session
        from features.rclone.remote_resources import RemoteResources
        from commonUtils.integrations.wrappers.cmdShellWrapper.binary import run_bytes
        from features.video.playback import VideoContent
        from features.video.transport import VideoTransport
        binary = executable.get_rclone_path()
        if not binary.is_file():
            self.skipTest('Pinned rclone is unavailable')
        with scratch() as root, crypt_fixture(root, binary) as fixture, patch.object(
                executable, 'get_rclone_path', return_value=binary):
            fixtures = codec_matrix(root)
            movies = [fixtures[0][3], next(path for container, video, audio, path in fixtures
                                         if container == 'avi' and video == 'mpeg4')]
            for movie in movies:
                environment, source, destination = session.launch(fixture.context, movie, 'Secret:' + movie.name)
                run_bytes([str(binary), '--config', session.NULL_CONFIG, 'copyto', str(source), str(destination)],
                          environment=environment, max_output=0)
            values = session.credentials(fixture.context)
            session.remember(fixture.context, dict(values, Plain=dict(type='alias', remote=str(movie.parent))))
            for remote, key in [(remote, movie.name) for movie in movies for remote in ('Plain', 'Secret')]:
                with self.subTest(remote=remote):
                    provider = RemoteResources(fixture.context, remote, binary=binary)
                    content = VideoContent(provider, key)
                    transport = VideoTransport(content)
                    player = QMediaPlayer()
                    sink, output = QVideoSink(), QAudioBufferOutput()
                    player.setVideoSink(sink)
                    player.setAudioBufferOutput(output)
                    frames, samples, errors = [], [], []
                    sink.videoFrameChanged.connect(lambda frame: frames.append(frame.startTime()) if frame.isValid() else None)
                    output.audioBufferReceived.connect(lambda buffer: samples.append(buffer.frameCount()) if buffer.isValid() else None)
                    player.errorOccurred.connect(lambda error, message: errors.append(message))
                    try:
                        player.setSource(qt.QUrl(transport.url))
                        player.play()
                        self.wait_until(lambda: (frames and samples) or errors, timeout=30)
                        self.assertFalse(errors, errors)
                        self.assertTrue(frames, 'No cloud video frames')
                        self.assertTrue(samples, 'No cloud audio samples')
                        player.pause()
                        player.setPosition(1000)
                        self.assertTrue(player.isSeekable())
                    finally:
                        player.stop()
                        player.setSource(qt.QUrl())
                        transport.close()
                        content.close()
                        provider.close()
                        player.deleteLater()
