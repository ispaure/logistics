"""Exercise track changes through the desktop player adapters."""
import shutil
import subprocess
from types import SimpleNamespace as NS
from unittest import skipUnless
from unittest.mock import Mock, patch

from commonUtils.testing.stages import TestStage, stage
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.video.ui.backend import AUDIO_SWITCH_TIMEOUT
from features.video.ui.mpv_backend import ColourPlayer
from features.video.ui.vlc_backend import VLCPlayer

TEST_STAGE = TestStage.REGRESSION


class AudioSwitchTests(QtTestCase):
    def vlc_player(self, *, seekable=True):
        native = Mock()
        native.get_state.return_value = 'playing'
        native.get_time.return_value = 4000
        native.is_seekable.return_value = seekable
        native.audio_get_track.return_value = 1
        native.audio_set_track.side_effect = lambda track: setattr(native.audio_get_track, 'return_value', track) or 0
        native.play.return_value = 0
        vlc = NS(State=NS(Playing='playing', Paused='paused'),
                 EventType=NS(MediaPlayerBuffering=1), MediaStats=Mock)
        owner = qt.QWidget()
        owner.playback_permitted = lambda: True
        with patch.object(VLCPlayer, 'make_callbacks', return_value=[Mock() for _ in range(5)]):
            player = VLCPlayer(vlc, NS(media_player_new=lambda: native), Mock(), owner)
        self.addCleanup(owner.deleteLater)
        player.timer.stop()
        player.media = Mock()
        player._tracks = (((1, 'First'), (2, 'Second'), (3, 'Third')), ())
        player.set_state(player.PlaybackState.PlayingState)
        return player, native

    def buffering(self, player, percent):
        player.audio_switch_buffering(NS(u=NS(new_cache=percent)))

    def test_vlc_holds_through_completion_and_uses_post_buffer_audio(self):
        player, native = self.vlc_player()
        states = []
        player.audioSwitchChanged.connect(lambda *state: states.append(state))
        player.setActiveAudioTrack(1)
        self.assertFalse(player.audio.suppressed, 'Readiness polling must not consume muted audio')
        player.poll_audio_switch('playing', 4000, 15)
        native.set_time.assert_called_once_with(4000)
        self.buffering(player, 100)
        player.poll_audio_switch('playing', 4010, 20)
        self.assertEqual(states, [(True, '')])
        self.buffering(player, 0)
        self.buffering(player, 100)
        player.poll_audio_switch('playing', 4010, 24)
        self.assertEqual(player.position(), 4000)
        self.assertEqual(states, [(True, '')])
        player.poll_audio_switch('playing', 4020, 25)
        self.assertEqual(states, [(True, ''), (False, '')])

    def test_vlc_rapid_selection_and_seek_wait_for_latest_native_cycle(self):
        player, native = self.vlc_player()
        player.setActiveAudioTrack(1)
        player.poll_audio_switch('playing', 4000, 15)
        self.buffering(player, 0)
        player.setActiveAudioTrack(2)
        player.setPosition(9000)
        player.poll_audio_switch('playing', 4100, 18)
        self.assertEqual(native.audio_get_track(), 2)
        self.buffering(player, 100)
        player.poll_audio_switch('playing', 4200, 24)
        self.assertEqual(native.audio_get_track(), 3)
        native.set_time.assert_called_with(9000)
        # A prior completion alone cannot release the newer request.
        self.buffering(player, 100)
        player.poll_audio_switch('playing', 9000, 26)
        self.assertIsNotNone(player._audio_switch)
        self.buffering(player, 0)
        self.buffering(player, 100)
        player.poll_audio_switch('playing', 9000, 27)
        player.poll_audio_switch('playing', 9030, 28)
        self.assertIsNone(player._audio_switch)

    def test_vlc_pauses_on_failure_and_never_resumes_manual_pause(self):
        player, native = self.vlc_player()
        player.setActiveAudioTrack(1)
        player.poll_audio_switch('playing', 4000, 15)
        player.pause()
        with patch('features.video.ui.vlc_backend.monotonic', return_value=AUDIO_SWITCH_TIMEOUT + 100):
            self.buffering(player, 0)
            self.buffering(player, 100)
            player.poll_audio_switch('paused', 4000, 20)
            player.poll_audio_switch('paused', 4000, 21)
            self.assertIsNotNone(player._audio_switch)
            native.play.assert_not_called()
            player.play()
        responses = []
        player.audioSwitchChanged.connect(lambda *state: responses.append(state))
        with patch('features.video.ui.vlc_backend.monotonic', return_value=AUDIO_SWITCH_TIMEOUT + 110):
            player.poll_audio_switch('playing', 4000, 21)
        self.assertEqual(player.playbackState(), player.PlaybackState.PausedState)
        self.assertEqual(player.position(), 4000)
        self.assertFalse(responses[0][0])
        self.assertIn('Could not switch audio', responses[0][1])
        native.play.assert_called_once()

    def test_vlc_unseekable_switch_pauses_and_stop_cancels_future_completion(self):
        player, native = self.vlc_player(seekable=False)
        player.setActiveAudioTrack(1)
        player.poll_audio_switch('playing', 4000, 15)
        native.audio_set_track.assert_not_called()
        self.assertEqual(player.playbackState(), player.PlaybackState.PausedState)
        native.is_seekable.return_value = True
        player.setActiveAudioTrack(2)
        player.poll_audio_switch('paused', 4000, 15)
        player.stop()
        self.buffering(player, 100)
        self.assertEqual(player.playbackState(), player.PlaybackState.StoppedState)
        self.assertIsNone(player._audio_seek)
        native.play.assert_not_called()

    def test_mpv_requires_latest_seek_restart_and_selected_audio_output(self):
        owner = qt.QWidget()
        owner.playback_permitted = lambda: True
        core, video = Mock(), Mock()
        player = ColourPlayer(core, video, owner)
        self.addCleanup(owner.deleteLater)
        player.colour_timer.stop()
        player._tracks = [dict(type='audio', id=i, selected=i == 1) for i in (1, 2, 3)]
        player._loaded = True
        player._position = 4000
        player.set_state(player.PlaybackState.PlayingState)
        player.setActiveAudioTrack(1)
        self.assertFalse(player.audio.suppressed, 'The native seek owns coordinated A/V buffering')
        old = player._audio_switch.serial
        player.setActiveAudioTrack(2)
        player.setPosition(9000)
        latest = player._audio_switch.serial
        core.submit.assert_called_with('switch-audio', latest, 3, 9000)
        player._tracks[0]['selected'] = False
        player._tracks[2]['selected'] = True
        player.update_audio_switch({'audio-switch': (old, 'restarted'), 'seeking': False, 'audio-pts': 9}, 9000)
        player.update_audio_switch({'audio-switch': (latest, 'restarted'), 'seeking': False}, 9000)
        self.assertEqual(player.position(), 9000)
        self.assertIsNotNone(player._audio_switch)
        player.pause()
        player.update_audio_switch({'audio-switch': (latest, 'restarted'), 'seeking': False, 'audio-pts': 9}, 9000)
        self.assertIsNone(player._audio_switch)
        self.assertEqual(player.playbackState(), player.PlaybackState.PausedState)

    @stage(TestStage.EXTENDED)
    @skipUnless(shutil.which('ffmpeg'), 'FFmpeg track muxer is required')
    def test_pinned_vlc_restarts_audio_during_playback_and_after_manual_pause(self):
        from logistics_build.build_retention import scratch
        from tests.readers.decoder_fixtures import headless_vlc_playback

        with scratch() as root:
            path = root / 'switch.mkv'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=192x108:rate=25',
                '-f', 'lavfi', '-i', 'sine=frequency=440', '-f', 'lavfi', '-i', 'sine=frequency=660',
                '-t', '16', '-map', '0:v', '-map', '1:a', '-map', '2:a',
                '-c:v', 'libx264', '-g', '25', '-c:a', 'aac', str(path)], check=True, timeout=30)
            owner = qt.QWidget()
            owner.playback_permitted = lambda: True
            backend = headless_vlc_playback(owner)
            player = backend.player
            states = []
            player.audioSwitchChanged.connect(lambda *state: states.append(state))
            try:
                player.setSource(qt.QUrl.fromLocalFile(str(path)))
                player.play()
                self.wait_until(lambda: len(player.audioTracks()) == 2 and player.position() > 1000)
                player.setActiveAudioTrack(1)
                held = player.position()
                self.assertFalse(player.audio.suppressed)
                self.assertEqual(states, [(True, '')])
                self.wait_until(lambda: len(states) == 2, timeout=6)
                self.assertEqual(states[-1], (False, ''))
                self.assertEqual(player.native.audio_get_track(), player._tracks[0][1][0])
                self.assertGreaterEqual(player.position(), held - 200)
                player.pause()
                self.wait_until(lambda: player.native.get_state() == player.vlc.State.Paused)
                player.setActiveAudioTrack(0)
                held = player.position()
                self.wait_until(lambda: player.native.audio_get_track() == player._tracks[0][0][0])
                self.assertEqual(states[-1], (True, ''))
                self.assertEqual(player.position(), held)
                self.assertEqual(player.native.get_state(), player.vlc.State.Paused)
                player.play()
                self.wait_until(lambda: len(states) == 4, timeout=6)
                self.assertEqual(states[-1], (False, ''))
                self.wait_until(lambda: player.position() > held + 250)
            finally:
                backend.retire()
                owner.deleteLater()
