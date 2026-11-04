"""Real desktop decoder and stable overlay acceptance for mobile parity."""

from collections import deque
from pathlib import Path
import shutil
import subprocess
from contextlib import contextmanager
from threading import Event
from unittest.mock import patch

from commonUtils.testing.stages import TestStage
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.selection import ResourceChoice

TEST_STAGE = TestStage.EXTENDED


class DesktopVideoParityTests(QtTestCase):
    def test_selected_speed_changes_real_playback_clock_after_resume(self):
        from time import monotonic
        from features.video.ui.player import VideoWindow
        from features.video.ui.backend import QtPlayback
        from features.video.ui.vlc_backend import VLCPlayback
        from PySide6.QtMultimedia import QMediaFormat
        from logistics_build.build_retention import scratch
        from tests.readers.video_fixtures import bundled_movie
        with scratch() as root:
            path = bundled_movie('speed-with-audio.mkv', root)
            factories = [lambda owner: VLCPlayback(owner, interactive=False)]
            # Qt is the retained compatibility adapter. The default VLC path
            # must also work on Linux hosts without a Qt Multimedia decoder.
            if QMediaFormat().supportedFileFormats(QMediaFormat.ConversionMode.Decode):
                factories.append(QtPlayback)
            for factory in factories:
                with patch('commonUtils.filesystem.storage.cache_directory', return_value=root / 'settings'):
                    window = VideoWindow(ResourceChoice(LocalFiles(root), path.name), backend_factory=factory)
                window.audio.setVolume(0)
                if hasattr(window.player, 'native'):
                    window.player.native.audio_output_set('adummy')
                try:
                    window.show()
                    self.wait_until(lambda: window.have_frame and window.player.position() > 500, timeout=20)
                    for speed, paused in ((2.0, False), (.5, False), (1.5, True)):
                        if paused:
                            window.pause_requested()
                        window.change_setting('rate', speed)
                        if paused:
                            self.assertEqual(window.player.playbackState(), window.player.PlaybackState.PausedState)
                        window.seek_to(1000)
                        if paused:
                            window.toggle_play()
                        # Let the post-seek decoded clock drain audio queued at
                        # the previous rate before measuring its steady speed.
                        self.wait_until(lambda: window.have_frame and window.player.position() > 2500, timeout=10)
                        start, position = monotonic(), window.player.position()
                        self.wait_until(lambda: monotonic() - start >= 2, timeout=3)
                        actual = (window.player.position() - position) / ((monotonic() - start) * 1000)
                        self.assertAlmostEqual(actual, speed, delta=.35,
                            msg=f'{type(window.player).__name__}: requested {speed}×, observed {actual:.2f}×')
                finally:
                    window.close()

    def test_actual_stall_recovers_and_manual_pause_wins(self):
        if not shutil.which('ffmpeg'):
            self.skipTest('FFmpeg fixture generator required')
        from features.video.ui.player import VideoWindow
        from features.video.ui.vlc_backend import VLCPlayback
        from logistics_build.build_retention import scratch
        class Provider(LocalFiles):
            remote_storage = True
            def __init__(self, root):
                super().__init__(root)
                self.entered, self.release, self.blocked = Event(), Event(), Event()
            @contextmanager
            def open(self, path):
                with super().open(path) as stream:
                    provider = self
                    class SlowStream:
                        def __getattr__(self, name):
                            return getattr(stream, name)
                        def read(self, count=-1):
                            if provider.blocked.is_set():
                                provider.entered.set()
                                if not provider.release.wait(60):
                                    raise OSError('Controlled stall timed out')
                            else:
                                provider.release.wait(.2)  # Bound read-ahead before injecting a real stall.
                            return stream.read(count)
                    yield SlowStream()
        with scratch() as root:
            path = root / 'slow.mp4'
            subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                'testsrc2=size=1280x720:rate=15:duration=24', '-c:v', 'libx264', '-preset', 'ultrafast',
                '-threads', '1', '-b:v', '28M', '-minrate', '28M', '-maxrate', '28M', '-bufsize', '28M',
                '-x264-params', 'nal-hrd=cbr:filler=1', '-movflags', '+faststart', str(path)],
                check=True, timeout=60)
            for manual_pause in (False, True):
                with self.subTest(manual_pause=manual_pause):
                    provider = Provider(root)
                    with patch('commonUtils.filesystem.storage.cache_directory', return_value=root / str(manual_pause)):
                        window = VideoWindow(ResourceChoice(provider, path.name),
                            backend_factory=lambda owner: VLCPlayback(owner, interactive=False))
                    window.audio.setVolume(0)
                    try:
                        window.show()
                        self.wait_until(lambda: window.have_frame and window.frame_position > 1000, timeout=20)
                        provider.blocked.set()
                        self.wait_until(lambda: bool(window.network_waits), timeout=20)
                        start = window.frame_position
                        self.wait_until(lambda: window.frame_position > start + 500, timeout=5,
                            message='A prefetch wait paused playable frames')
                        self.wait_until(lambda: window.network_hold, timeout=20,
                            message=lambda: repr(dict(requested=window.requested_play,
                                clock=window.player.position(), frame=window.frame_position,
                                state=str(window.player.native.get_state()), waiting=len(window.network_waits),
                                displayed=window.player.stats.displayed_pictures,
                                status=window.status.text())))
                        held = window.player.position()
                        if manual_pause:
                            window.pause_requested()
                        provider.release.set()
                        self.wait_until(lambda: not window.network_waits, timeout=10)
                        if manual_pause:
                            self.assertFalse(window.requested_play)
                            self.assertEqual(window.player.playbackState(), window.player.PlaybackState.PausedState)
                            self.assertEqual(window.player.position(), held)
                        else:
                            self.wait_until(lambda: window.frame_position > held + 500, timeout=15,
                                message='Requested playback did not recover after real starvation')
                    finally:
                        provider.release.set()
                        window.close()

    def test_vtt_short_timestamps_and_cue_settings(self):
        from features.video.subtitles import Subtitles
        subtitles = Subtitles(b'WEBVTT\n\ncue-1\n00:01.000 --> 00:02.500 align:start\n<b>Visible</b>\n')
        self.assertEqual(subtitles.at(1500), 'Visible')
        self.assertEqual(subtitles.at(2500), '')

    def test_overlay_geometry_lock_and_readiness_do_not_resume_manual_pause(self):
        from features.video.ui.player import VideoWindow
        from logistics_build.build_retention import scratch
        with scratch() as root:
            (root / 'movie.mp4').write_bytes(b'fixture')
            with patch('commonUtils.filesystem.storage.cache_directory', return_value=root / 'state'):
                window = VideoWindow(ResourceChoice(LocalFiles(root), 'movie.mp4'))
            try:
                window.startup_pending = False
                window.show()
                qt.QApplication.processEvents()
                before = window.video_viewport.geometry()
                window.chrome.hide()
                qt.QApplication.processEvents()
                self.assertEqual(window.video_viewport.geometry(), before)
                window.show_controls()
                qt.QApplication.processEvents()
                self.assertEqual(window.video_viewport.geometry(), before)
                window.show_tools()
                next(button for button in window.settings_scroll.widget().findChildren(qt.QPushButton)
                     if button.text() == 'Lock controls').click()
                self.assertTrue(window.unlock_button.isVisible())
                self.assertFalse(window.chrome.isVisible())
                window.escape_playback()
                self.assertFalse(window.controls_locked)
                token = object()
                window.network_waiting(token, True)
                window.network_hold = True
                window.pause_requested()
                with patch.object(window.player, 'play') as play:
                    window.network_waiting(token, False)
                    play.assert_not_called()
                self.assertFalse(window.requested_play)
            finally:
                window.close()

    def test_vlc_frames_pause_offsets_and_retirement(self):
        from features.video.ui.player import VideoWindow
        from features.video.ui.vlc_backend import VLCPlayback
        from logistics_build.build_retention import scratch
        from tests.readers.video_fixtures import chapter_movie
        from features.video.session import PlaybackSettings
        with scratch() as root:
            path = chapter_movie(root)
            with patch('commonUtils.filesystem.storage.cache_directory', return_value=root / 'state'):
                window = VideoWindow(ResourceChoice(LocalFiles(root), path.name),
                    backend_factory=lambda owner: VLCPlayback(owner, interactive=False))
            frames = deque(maxlen=1)
            window.player.videoSink().videoFrameChanged.connect(
                lambda frame, frames=frames: frames.append(frame.toImage()) if frame.isValid() else None)
            try:
                window.show()
                self.wait_until(lambda: bool(frames) and window.player.position() >= 200, timeout=25)
                self.assertFalse(frames[-1].isNull())
                self.assertGreater(window.player.duration(), 10000)
                self.assertEqual(window.player.native.video_get_size(), (320, 180))
                self.assertEqual(frames[-1].size(), qt.QSize(320, 180))
                self.assertEqual([chapter.title for chapter in window.player.chapters()], ['Opening', 'Second scene'])
                window.player.configure(PlaybackSettings(subtitle_delay_ms=250, audio_delay_ms=150))
                self.assertEqual(window.player.native.video_get_spu_delay(), 250000)
                self.assertEqual(window.player.native.audio_get_delay(), 150000)
                window.pause_requested()
                self.assertFalse(window.requested_play)
                self.assertEqual(window.player.playbackState(), window.player.PlaybackState.PausedState)
                window.seek_to(6000)
                self.assertEqual(window.player.position(), 6000)
                window.show_receivers()
                self.assertEqual(window.panel_name, 'cast')
                self.assertTrue(window.settings_pane.isVisible())
                window.close_settings()
                output = Path(__file__).resolve().parents[3] / 'test-results/video-desktop-vlc'
                output.mkdir(parents=True, exist_ok=True)
                frames[-1].save(str(output / 'decoded-frame.png'))
                window.grab().save(str(output / 'player.png'))
            finally:
                window.close()
            self.assertTrue(window.player.retired)
            self.assertTrue(window.content.closed)

    def test_vlc_codec_matrix_decodes_frames_and_audio(self):
        from features.video.ui.player import VideoWindow
        from features.video.ui.vlc_backend import VLCPlayback
        from logistics_build.build_retention import scratch
        from tests.readers.video_fixtures import codec_matrix
        with scratch() as root:
            for container, video, audio, path in codec_matrix(root):
                with self.subTest(container=container, video=video, audio=audio):
                    with patch('commonUtils.filesystem.storage.cache_directory', return_value=root / 'state'):
                        window = VideoWindow(ResourceChoice(LocalFiles(root), path.name),
                            backend_factory=lambda owner: VLCPlayback(owner, interactive=False))
                    frames = deque(maxlen=1)
                    window.player.videoSink().videoFrameChanged.connect(
                        lambda frame, frames=frames: frames.append(frame.toImage()) if frame.isValid() else None)
                    try:
                        # A cloud guest has no speaker device; the dummy output
                        # still decodes audio and exposes the native statistics.
                        window.player.native.audio_output_set('adummy')
                        window.show()
                        stats = window.player.vlc.MediaStats()
                        def decoded():
                            return (frames and window.player.media.get_stats(stats)
                                and stats.decoded_audio > 0)
                        self.wait_until(decoded, timeout=25, message=lambda: repr(dict(
                            frames=len(frames), audio=stats.decoded_audio,
                            video=stats.decoded_video, state=str(window.player.native.get_state()),
                            tracks=window.player.native.audio_get_track_description())))
                        self.assertFalse(frames[-1].isNull())
                        window.pause_requested()
                        window.seek_to(1000)
                        self.assertEqual(window.player.position(), 1000)
                        self.assertFalse(window.requested_play)
                    finally:
                        window.close()

    def test_source_browser_retains_provider_after_player_closes(self):
        from features.video.ui.player import VideoWindow
        from features.video.ui.source_folder import VideoSourceFolder
        from logistics_build.build_retention import scratch
        class Provider(LocalFiles):
            leases = 0
            def acquire(self):
                self.leases += 1
                def release():
                    self.leases -= 1
                return release
        with scratch() as root:
            (root / 'movie.mp4').write_bytes(b'fixture')
            provider = Provider(root)
            with patch('commonUtils.filesystem.storage.cache_directory', return_value=root / 'state'):
                player = VideoWindow(ResourceChoice(provider, 'movie.mp4'))
            player.startup_pending = False
            browser = VideoSourceFolder(player.content)
            try:
                browser.show()
                self.wait_until(lambda: not browser.browser.busy)
                player.close()
                self.assertGreater(provider.leases, 0)
                self.assertTrue(browser.source.provider.entry('movie.mp4'))
                selected = browser.browser.views.selected_rows()
                self.assertEqual(len(selected), 1)
            finally:
                player.close()
                browser.close()
                self.wait_until(lambda: provider.leases == 0, drain_deferred=True)

    def test_native_subtitle_formats_render_real_cues(self):
        from features.video.ui.player import VideoWindow
        from features.video.ui.vlc_backend import VLCPlayback
        from logistics_build.build_retention import scratch
        from tests.readers.video_fixtures import bundled_movie
        formats = {
            'srt': '1\n00:00:00,000 --> 00:00:11,000\nWHITE CAPTION\n',
            'vtt': 'WEBVTT\n\n00:00.000 --> 00:11.000\nWHITE CAPTION\n',
            'ass': ('[Script Info]\nScriptType: v4.00+\nPlayResX: 320\nPlayResY: 180\n'
                '[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n'
                'Style: Default,Arial,24,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,10,10,10,1\n'
                '[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n'
                'Dialogue: 0,0:00:00.00,0:00:11.00,Default,,0,0,0,,WHITE CAPTION\n'),
            'ssa': ('[Script Info]\nScriptType: v4.00\nPlayResX: 320\nPlayResY: 180\n'
                '[V4 Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,TertiaryColour,BackColour,Bold,Italic,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,AlphaLevel,Encoding\n'
                'Style: Default,Arial,24,16777215,255,0,0,0,0,1,1,0,2,10,10,10,0,1\n'
                '[Events]\nFormat: Marked,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n'
                'Dialogue: Marked=0,0:00:00.00,0:00:11.00,Default,,0,0,0,,WHITE CAPTION\n'),
        }
        with scratch() as root:
            path = bundled_movie('black.mkv', root)
            provider = LocalFiles(root)
            diagnostics = Path(__file__).resolve().parents[3] / 'test-results/video-desktop-vlc'
            diagnostics.mkdir(parents=True, exist_ok=True)
            for extension, text in formats.items():
                with self.subTest(extension=extension):
                    (root / f'captions.{extension}').write_text(text, encoding='utf-8')
                    with patch('commonUtils.filesystem.storage.cache_directory', return_value=root / ('state-' + extension)):
                        window = VideoWindow(ResourceChoice(provider, path.name),
                            backend_factory=lambda owner: VLCPlayback(owner, interactive=False))
                    frames = deque(maxlen=1)
                    window.player.videoSink().videoFrameChanged.connect(
                        lambda frame, frames=frames: frames.append(frame.toImage()) if frame.isValid() else None)
                    try:
                        window.show()
                        self.wait_until(lambda: bool(frames), timeout=20)
                        frames.clear()
                        choice = ResourceChoice(provider, f'captions.{extension}')
                        with patch('services.documents.ui.editors.choose_editor_resource', return_value=choice):
                            window.load_subtitles()
                        def caption_rendered():
                            if not frames:
                                return False
                            image = frames[-1]
                            gray = image.convertToFormat(qt.QImage.Format.Format_Grayscale8)
                            return sum(value > 80 for value in bytes(gray.constBits())) > 5
                        def subtitle_failure():
                            output = Path(__file__).resolve().parents[3] / 'test-results/video-desktop-vlc'
                            output.mkdir(parents=True, exist_ok=True)
                            if frames:
                                frames[-1].save(str(output / f'failed-{extension}.png'))
                            return repr(dict(time=window.player.native.get_time(),
                                subtitle=window.player.native.video_get_spu(),
                                tracks=window.player.native.video_get_spu_description(),
                                status=window.status.text(), frames=len(frames)))
                        self.wait_until(caption_rendered, timeout=15, message=subtitle_failure)
                        frames[-1].save(str(diagnostics / f'caption-{extension}.png'))
                        self.assertGreater(window.subtitle_tracks.count(), 1)
                        self.assertIsNotNone(window.external_selection)
                        self.assertGreaterEqual(window.player.native.video_get_spu(), 0)
                        selected = window.external_selection
                        if extension == 'srt':
                            def pixels(image):
                                gray = image.convertToFormat(qt.QImage.Format.Format_Grayscale8)
                                return sum(value > 80 for value in bytes(gray.constBits()))
                            original = pixels(frames[-1])
                            window.change_setting('subtitle_scale', 2.0)
                            frames.clear()
                            self.wait_until(lambda: frames and pixels(frames[-1]) > original * 1.4,
                                timeout=20, message='Subtitle size did not change rendered cues')
                        window.select_subtitle(window.subtitle_tracks.findData(-1))
                        frames.clear()
                        self.wait_until(lambda: frames and not caption_rendered(), timeout=10,
                            message='Subtitles Off left a rendered cue')
                        self.assertEqual(window.player.native.video_get_spu(), -1)
                        window.select_subtitle(window.subtitle_tracks.findData(selected))
                        frames.clear()
                        self.wait_until(caption_rendered, timeout=15, message=subtitle_failure)
                    finally:
                        window.close()
