"""Native audio tails, A/V endpoint and caption restoration with video."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from collections import deque
from pathlib import Path
import shutil
import subprocess
from time import monotonic
from types import SimpleNamespace as NS
from unittest import skipUnless
from unittest.mock import Mock, patch

from commonUtils.testing.stages import TestStage, stage
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.selection import ResourceChoice

TEST_STAGE = TestStage.EXTENDED


class TailCaptionTests(QtTestCase):
    @stage(TestStage.REGRESSION)
    def test_unknown_tail_end_times_out_without_claiming_completion(self):
        from features.video.ui.backend import SEEK_TIMEOUT
        from features.video.ui.vlc_backend import OutputObservation, VLCPlayer
        owner = qt.QWidget()
        self.addCleanup(owner.deleteLater)
        owner.content = NS(media_bounds=None)
        native = Mock()
        native.get_time.return_value = 10000
        vlc = NS(MediaStats=Mock, EventType=NS(MediaPlayerBuffering=1))
        with patch.object(VLCPlayer, 'make_callbacks', return_value=[Mock() for _ in range(5)]):
            player = VLCPlayer(vlc, NS(media_player_new=lambda: native), Mock(), owner)
        player.timer.stop()
        player._state = player.PlaybackState.PlayingState
        player._audio_only = True
        player._position = 10000
        player.stats = NS(decoded_audio=500, played_abuffers=430, decoded_video=250, displayed_pictures=250)
        player._clock_observation = OutputObservation(10000, 500, 430, 250, 250, 0, 0)
        statuses = []
        player.mediaStatusChanged.connect(statuses.append)
        player.stats.played_abuffers += 1
        with patch('features.video.ui.vlc_backend.monotonic', return_value=SEEK_TIMEOUT + 1):
            self.assertFalse(player.observe_output(10000), 'Delivered audio still proves live output')
        with patch('features.video.ui.vlc_backend.monotonic', return_value=SEEK_TIMEOUT * 2 + 2):
            self.assertTrue(player.observe_output(10000))
        self.assertEqual(player.playbackState(), player.PlaybackState.PausedState)
        self.assertEqual(player.error(), player.Error.ResourceError)
        self.assertNotIn(player.MediaStatus.EndOfMedia, statuses)

    @stage(TestStage.REGRESSION)
    def test_explicit_seek_after_completion_overrides_replay_at_zero(self):
        from features.video.ui.vlc_backend import VLCPlayer
        player = NS(retired=False, _completed=True, _external_route=False,
                    in_audio_tail=lambda target: False, reopen_at=Mock(), seek_at=Mock())
        VLCPlayer.setPosition(player, 4500)
        player.reopen_at.assert_called_once_with(4500)
        player.seek_at.assert_not_called()

    @skipUnless(shutil.which('ffmpeg'), 'FFmpeg synthetic fixture generator required')
    def test_vlc_audio_tail_pause_and_normal_video_caption_restoration(self):
        from features.video.ui.player import VideoWindow
        from logistics_build.build_retention import scratch
        from tests.readers.decoder_fixtures import headless_vlc_playback

        evidence = Path(__file__).resolve().parents[3] / 'test-results/video-tail-captions'
        evidence.mkdir(parents=True, exist_ok=True)
        with scratch() as root:
            captions = root / 'embedded.srt'
            captions.write_text('1\n00:00:00,500 --> 00:00:02,500\nBASELINE WHITE\n\n'
                '2\n00:00:04,000 --> 00:00:06,000\nTAIL FOUR SIX\n\n'
                '3\n00:00:11,000 --> 00:00:14,000\nTAIL ELEVEN FOURTEEN\n\n'
                '4\n00:00:20,000 --> 00:00:22,000\nMUST NOT EXTEND PLAYBACK\n')
            for codec in ('srt', 'ass'):
                path = root / (codec + '.mkv')
                subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                    'color=c=blue:s=320x180:r=25:d=3', '-f', 'lavfi', '-i',
                    'sine=frequency=440:duration=15', '-i', str(captions), '-map', '0:v',
                    '-map', '1:a', '-map', '2:s', '-c:v', 'libx264', '-preset', 'ultrafast',
                    '-g', '25', '-c:a', 'aac', '-c:s', codec, '-disposition:s:0', 'default', str(path)],
                    check=True, timeout=30)
                with self.subTest(codec=codec), patch('commonUtils.filesystem.storage.cache_directory',
                        return_value=root / ('state-' + codec)):
                    window = VideoWindow(ResourceChoice(LocalFiles(root), path.name),
                        backend_factory=headless_vlc_playback)
                    frames = deque(maxlen=1)
                    window.player.videoSink().videoFrameChanged.connect(
                        lambda frame, frames=frames: frames.append(frame.toImage()) if frame.isValid() else None)
                    def visible(images=frames):
                        if not images:
                            return False
                        image = images[-1].convertToFormat(qt.QImage.Format.Format_Grayscale8)
                        return sum(value > 100 for value in bytes(image.constBits())) > 30
                    def details():
                        return repr(dict(time=window.player.position(), native=window.player.native.get_time(),
                            state=str(window.player.native.get_state()), spu=window.player.native.video_get_spu(),
                            video=window.player.native.video_get_track(), pending=window.player._pending_seek,
                            visible=visible(), target=window.player._seek_target, status=window.status.text()))
                    try:
                        window.show()
                        self.wait_until(lambda: window.content.media_bounds and visible()
                            and 600 <= window.player.position() <= 2300, timeout=20, message=details)
                        original_video = window.player.native.video_get_track()
                        original_audio = window.player.native.audio_get_track()
                        original_subtitle = window.player.native.video_get_spu()
                        frames[-1].save(str(evidence / f'production-{codec}-baseline.png'))
                        window.seek_to(11500)
                        frames.clear()
                        self.wait_until(lambda: window.player._audio_only
                            and 11700 <= window.player.native.get_time() <= 13500, timeout=12, message=details)
                        self.assertEqual(window.player.native.video_get_track(), -1)
                        self.assertEqual(window.player.native.audio_get_track(), original_audio)
                        played = window.player.stats.played_abuffers
                        self.wait_until(lambda: window.player.stats.played_abuffers > played,
                            timeout=3, message=details)
                        window.pause_requested()
                        self.wait_until(lambda: window.player.native.get_state() == window.player.vlc.State.Paused)
                        held = window.player.position()
                        native_held = window.player.native.get_time()
                        until = monotonic() + .6
                        self.wait_until(lambda: monotonic() >= until)
                        self.assertEqual(window.player.position(), held)
                        self.assertEqual(window.player.native.get_time(), native_held)
                        window.seek_to(1000)
                        frames.clear()
                        self.wait_until(lambda: visible() and not window.player._audio_only
                            and 800 <= window.player.position() <= 1500, timeout=12, message=details)
                        self.assertEqual(window.player.native.video_get_track(), original_video)
                        self.assertEqual(window.player.native.video_get_spu(), original_subtitle)
                        self.assertEqual(window.player.playbackState(), window.player.PlaybackState.PausedState)
                        frames[-1].save(str(evidence / f'production-{codec}-backseek.png'))
                        window.seek_to(11500)
                        frames.clear()
                        self.wait_until(lambda: window.player._audio_only
                            and window.player.native.get_state() == window.player.vlc.State.Paused,
                            timeout=12, message=details)
                        self.assertFalse(window.requested_play)
                        self.assertAlmostEqual(window.player.native.get_time(), 11500, delta=500)
                        window.toggle_play()
                        self.wait_until(lambda: window.ended, timeout=10, message=details)
                        self.assertLess(window.player.duration(), 16000)
                        self.assertEqual(window.player.playbackState(), window.player.PlaybackState.StoppedState)
                        self.assertFalse(window.requested_play)
                        frames.clear()
                        window.toggle_play()
                        self.wait_until(lambda: not window.player._audio_only and visible()
                            and 600 <= window.player.native.get_time() <= 2300
                            and window.player.stats.played_abuffers > 0, timeout=12, message=details)
                        self.assertEqual(window.player.native.video_get_track(), original_video)
                        self.assertEqual(window.player.native.audio_get_track(), original_audio)
                        self.assertEqual(window.player.native.video_get_spu(), original_subtitle)
                    finally:
                        window.close()
