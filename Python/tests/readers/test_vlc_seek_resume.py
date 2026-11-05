"""Execute production resume/presentation methods without a decoder or GUI."""
import ast
from pathlib import Path
from threading import Lock
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
SOURCE = Path(__file__).resolve().parents[2] / 'features/video/ui/vlc_backend.py'


def method(name, source=SOURCE):
    tree = ast.parse(source.read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'VLCPlayer')
    node = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name)
    scope = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), scope)
    return scope[name]


PLAY = method('play')
PRESENT = method('present_picture')


class SeekResumeTests(unittest.TestCase):
    def player(self, *, native_time=11655, held=11655, pending=None):
        player = NS(retired=False, parent=lambda: NS(playback_permitted=lambda: True),
            native=NS(play=Mock(return_value=0), get_time=Mock(return_value=native_time)),
            media=object(), audio=NS(suppress=Mock()), _held_position=held,
            _pending_seek=pending, setPosition=Mock(), set_state=Mock(),
            PlaybackState=NS(PausedState='paused', PlayingState='playing'),
            generation=7, seek_generation=3, _state='playing', _paused_preview_target=None,
            _buffer_lock=Lock(), _source_size=None, read_metadata=Mock(),
            video=NS(videoSink=Mock(return_value=NS(setImage=Mock()))), presentation_current=False)
        return player

    def test_exact_current_clock_resume_never_starts_a_seek(self):
        player = self.player()
        PLAY(player)
        player.setPosition.assert_not_called()
        self.assertIsNone(player._held_position)
        self.assertIsNone(player._pending_seek)
        self.assertEqual(player.seek_generation, 3)
        player.set_state.assert_called_once_with('playing')

    def test_actual_new_frames_present_after_exact_noop_resume(self):
        player = self.player()
        def seek(value):
            player._pending_seek = value
            player.seek_generation += 1
        player.setPosition.side_effect = seek
        PLAY(player)
        frame = object()
        PRESENT(player, frame, (7, 3, player._pending_seek is None))
        player.video.videoSink().setImage.assert_called_once_with(frame)
        self.assertTrue(player.presentation_current)

    def test_different_native_clock_still_performs_real_seek(self):
        for clock in (11654, 11656, 18000):
            with self.subTest(clock=clock):
                player = self.player(native_time=clock)
                PLAY(player)
                player.setPosition.assert_called_once_with(11655)
                self.assertIsNone(player._held_position)

    def test_explicit_pending_seek_is_never_elided_even_at_target_clock(self):
        player = self.player(pending=11655)
        PLAY(player)
        player.setPosition.assert_called_once_with(11655)

    def test_old_seek_or_source_generation_and_preseek_frames_remain_rejected(self):
        for generation in ((7, 2, True), (6, 3, True), (7, 3, False)):
            with self.subTest(generation=generation):
                player = self.player()
                PLAY(player)
                PRESENT(player, object(), generation)
                player.video.videoSink().setImage.assert_not_called()
                self.assertFalse(player.presentation_current)

    def test_preserved_manual_pause_remains_paused(self):
        player = self.player()
        PLAY(player, preserve_pause=True)
        player.setPosition.assert_not_called()
        self.assertTrue(player._pause_after_open)
        player.audio.suppress.assert_called_once_with(True)
        player.set_state.assert_called_once_with('paused')

    def test_no_held_position_never_queries_clock_or_seeks(self):
        player = self.player(held=None)
        PLAY(player)
        player.native.get_time.assert_not_called()
        player.setPosition.assert_not_called()

    def test_denied_or_retired_playback_cannot_touch_seek_or_native_play(self):
        for retired in (False, True):
            player = self.player()
            player.retired = retired
            player.parent = lambda: NS(playback_permitted=lambda: False)
            PLAY(player)
            player.native.play.assert_not_called()
            player.setPosition.assert_not_called()


if __name__ == '__main__':
    unittest.main()
