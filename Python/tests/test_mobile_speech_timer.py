"""Listening budgets use elapsed playback time, including delayed loop callbacks."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from features.books.mobile.speech import PlaybackTimer


class PlaybackTimerTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.loop = Mock()
        self.loop.call_later.side_effect = lambda *args: Mock()
        self.changed, self.expired = Mock(), Mock()
        self.timer = PlaybackTimer(self.loop, changed=self.changed, expired=self.expired,
            clock=lambda: self.now)

    def tick(self, seconds):
        self.now += seconds
        self.timer._cancel()
        self.timer._tick()

    def test_pause_resume_retains_fractional_budget_and_expires_once(self):
        self.timer.select(900)
        self.tick(50)
        self.assertEqual(self.timer.remaining, 900)
        self.timer.set_running(True)
        self.now += 20.25
        self.timer.set_running(False)
        self.assertEqual(self.timer.remaining, 879.75)
        self.tick(100)
        self.assertEqual(self.timer.remaining, 879.75)
        self.timer.set_running(True)
        deadline = self.timer.deadline
        self.now += 10
        self.timer.set_running(True)  # Another utterance does not restart it.
        self.assertEqual(self.timer.deadline, deadline)
        self.tick(1000)  # A late callback still enforces the full elapsed time.
        self.assertEqual(self.timer.remaining, 0)
        self.expired.assert_called_once_with()
        self.assertIsNone(self.timer.handle)
        self.timer.set_running(True)
        self.assertEqual(self.timer.remaining, 900)

    def test_reset_duration_changes_off_and_disposal(self):
        self.timer.select(1800)
        self.timer.set_running(True)
        self.tick(60)
        handle = self.timer.handle
        self.timer.reset()
        handle.cancel.assert_called_once_with()
        self.assertEqual(self.timer.remaining, 1800)
        self.tick(60)
        self.timer.set_running(False)
        self.timer.reset()
        self.tick(100)
        self.assertEqual(self.timer.remaining, 1800)
        self.assertIsNone(self.timer.handle)
        self.timer.select(2700)
        self.timer.set_running(True)
        self.tick(60)
        self.timer.select(3600)
        self.assertEqual(self.timer.remaining, 3600)
        self.timer.select(0)
        self.tick(10000)
        self.expired.assert_not_called()
        self.assertIsNone(self.timer.handle)
        self.timer.select(900)
        handle = self.timer.handle
        self.timer.dispose()
        handle.cancel.assert_called_once_with()
        self.assertIsNone(self.timer.handle)
        self.assertFalse(self.timer.running)


class NativeMediaTimerTests(unittest.TestCase):
    def test_apple_subtitle_updates_without_reactivating_audio(self):
        from features.books.mobile.media_ios import AppleMedia
        media = AppleMedia.__new__(AppleMedia)
        media.closed = False
        media.title = 'Read aloud'
        media.audio, media.info = Mock(), SimpleNamespace()
        media._key = lambda name: name
        with patch.dict('sys.modules', {'rubicon.objc': SimpleNamespace(ns_from_py=lambda value: value)}):
            media.update('speaking', timer_text='Time remaining: 15:00')
            media.audio.setActive.assert_called_once_with(True, error=None)
            self.assertEqual(media.info.nowPlayingInfo['MPMediaItemPropertyArtist'], 'Time remaining: 15:00')
            media.update_timer('Time remaining: 14:59')
            self.assertEqual(media.info.nowPlayingInfo['MPMediaItemPropertyArtist'], 'Time remaining: 14:59')
            media.audio.setActive.assert_called_once()
            media.update('paused', timer_text='Time remaining: 14:59')
            self.assertEqual(media.info.nowPlayingInfo['MPNowPlayingInfoPropertyPlaybackRate'], 0)
            media.update_timer('Time remaining: 30:00')
            self.assertEqual(media.info.playbackState, 2)
            self.assertEqual(media.info.nowPlayingInfo['MPNowPlayingInfoPropertyPlaybackRate'], 0)
            media.update_timer('')
            self.assertEqual(media.info.nowPlayingInfo['MPMediaItemPropertyArtist'], 'Logisticks')
            media.update_content('Book.epub')
            self.assertEqual(media.info.nowPlayingInfo['MPMediaItemPropertyTitle'], 'Book.epub')
            self.assertEqual(media.info.nowPlayingInfo['MPMediaItemPropertyArtist'], 'Logisticks')
            media.update_timer('Time remaining: 15:00')
            self.assertEqual(media.info.nowPlayingInfo['MPMediaItemPropertyArtist'],
                'Time remaining: 15:00')
            self.assertEqual(media.info.playbackState, 2)
            media.closed = True
            media.update_content('ignored')
            self.assertEqual(media.info.nowPlayingInfo['MPMediaItemPropertyTitle'], 'Book.epub')

    def test_android_timer_refresh_uses_metadata_only_path(self):
        from features.books.mobile.media_android import AndroidMedia
        media = AndroidMedia.__new__(AndroidMedia)
        media.closed, media.service, media.context = False, Mock(), object()
        media.update('speaking', timer_text='Time remaining: 15:00')
        media.service.update.assert_called_once_with(media.context, True, 'Time remaining: 15:00')
        media.update_timer('Time remaining: 14:59')
        media.service.updateTimer.assert_called_once_with(media.context, 'Time remaining: 14:59')
        media.service.update.assert_called_once()
        media.update('paused', timer_text='Time remaining: 14:59')
        media.service.update.assert_called_with(media.context, False, 'Time remaining: 14:59')
        media.update_timer('')
        media.service.updateTimer.assert_called_with(media.context, '')
        media.update_content('Book.epub')
        media.service.updateContent.assert_called_once_with(media.context, 'Book.epub')
        media.closed = True
        media.update_timer('ignored')
        media.update_content('ignored')
        media.service.updateContent.assert_called_once()
        self.assertEqual(media.service.updateTimer.call_count, 2)


if __name__ == '__main__':
    unittest.main()
