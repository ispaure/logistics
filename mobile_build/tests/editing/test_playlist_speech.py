"""Playlist sequencing through the mobile speech panel and media commands."""

import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

import toga
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.stages import TestStage
from features.notes_library.mobile.playlist_speech import PlaylistSpeech
from features.notes_library.notes import NotesLibrary
from features.notes_library.playlists import PlaylistStore
from features.books.mobile.media_controls import SpeechPlayback, enforce_privacy
from features.books.mobile.speech_host import SpeechPresentation
from mobile.preferences import Preferences
from mobile_build.tests.editing.test_markdown_speech import Engine
from mobile_build.tests.editing.test_speech_media import Media

TEST_STAGE = TestStage.REGRESSION


class PlaylistSpeechTests(unittest.TestCase):
    def exercise(self, fixture, *, protected=False):
        async def run():
            with TemporaryDirectory() as directory:
                root = Path(directory)
                provider = LocalFiles(root)
                provider.private = protected
                owner = SimpleNamespace(cancelled=Event(), valid=lambda: not privacy.resume_locked,
                                        path=None, view=toga.Box())
                privacy = SimpleNamespace(inactive=False, interrupted=False, captured=False,
                                          resume_locked=False, sensitive=lambda: protected)
                app = SimpleNamespace(private_root=root, loop=asyncio.get_running_loop(),
                                      active_host=True, screen_privacy=privacy, preferences=Preferences(root))
                app.speech_presentation = SpeechPresentation(
                    playback=lambda panel, **kw: SpeechPlayback(panel, app, factory=Media, **kw))
                library = NotesLibrary(provider)
                catalog = PlaylistStore(root, app=app).for_library(library)
                record = catalog.create('Private queue' if protected else 'Queue')
                for path, source in (
                        ('a.md', ' '.join('alpha' + str(i) for i in range(55))),
                        ('empty.md', '![Hidden alt](inaccessible.png)'),
                        ('b.md', ' '.join('bravo' + str(i) for i in range(20))),
                        ('c.md', ' '.join('charlie' + str(i) for i in range(70)))):
                    (root / path).write_text(source)
                    record = catalog.add(record.id, path)
                speech = PlaylistSpeech(owner, catalog, lambda: None, app=app)
                try:
                    with patch('features.books.mobile.speech_view.NativeSpeech', Engine):
                        await fixture(speech, record, library, app, privacy)
                finally:
                    speech.close()
                    if speech.save_task is not None:
                        await speech.save_task
                    library.close()
        asyncio.run(run())

    async def idle(self, speech):
        for _ in range(100):
            if speech.work is None or speech.work.done():
                return
            await asyncio.sleep(.01)
        self.fail('Playlist did not complete the requested transition')

    def test_media_skips_across_empty_entry_and_deletion_retires_session(self):
        async def fixture(speech, record, library, app, privacy):
            speech.play(record.id)
            await self.idle(speech)
            panel = speech.panel
            media = panel.playback.media
            self.assertEqual(speech.active_id, record.entries[0].id)
            self.assertTrue(panel.playback.command('pause'))
            self.assertTrue(panel.playback.command('forward'))
            self.assertTrue(panel.playback.command('forward'))
            await self.idle(speech)
            self.assertEqual(speech.active_id, record.entries[3].id)
            self.assertEqual(speech.state, 'paused')
            self.assertTrue(panel.playback.command('back'))
            await self.idle(speech)
            self.assertEqual(speech.active_id, record.entries[0].id)
            self.assertIs(panel.playback.media, media)
            speech.catalog.delete(record.id)
            for _ in range(30):
                if speech.panel is None:
                    break
                await asyncio.sleep(.01)
            self.assertIsNone(speech.panel)
            self.assertTrue(media.closed)
            self.assertFalse(panel.playback.command('play'))
            self.assertIsNone(speech.catalog.get(record.id))
        self.exercise(fixture)

    def test_opt_in_allows_prepared_text_only_and_revocation_retires_media(self):
        async def fixture(speech, record, library, app, privacy):
            app.preferences.save(session_speech_when_locked='true')
            # Entry 2 is the adjacent playable passage. The following passage
            # remains unprepared because lock occurs before advancing to it.
            speech.play(record.id, record.entries[2].id)
            await self.idle(speech)
            if speech.preload is not None:
                await speech.preload
            panel = speech.panel
            media = panel.playback.media
            self.assertEqual(media.title, 'Read aloud')
            self.assertIn(record.entries[3], speech.queue.prepared)
            with patch.object(library, 'read', wraps=library.read) as read:
                privacy.inactive = privacy.resume_locked = True
                enforce_privacy(app)
                self.assertTrue(panel.playback.command('forward'))
                await self.idle(speech)
                self.assertEqual(speech.active_id, record.entries[3].id)
                self.assertTrue(panel.playback.command('back'))
                await self.idle(speech)
                self.assertEqual(speech.active_id, record.entries[2].id)
                self.assertTrue(panel.playback.command('back'))
                await self.idle(speech)
                self.assertIsNotNone(speech.waiting)
                self.assertEqual(speech.state, 'paused')
                read.assert_not_called()
                privacy.inactive = privacy.resume_locked = False
                enforce_privacy(app)
                panel.resume_playback()
                await self.idle(speech)
                self.assertEqual(speech.active_id, record.entries[0].id)
                self.assertEqual(speech.state, 'speaking')
                self.assertTrue(read.called)
                speech.catalog.revoked = lambda: True
                enforce_privacy(app)
                self.assertIsNone(speech.panel)
                self.assertTrue(media.closed)
                self.assertFalse(panel.playback.command('forward'))
        self.exercise(fixture, protected=True)

    def test_lock_opt_in_off_releases_text_and_media(self):
        async def fixture(speech, record, library, app, privacy):
            speech.play(record.id)
            await self.idle(speech)
            panel = speech.panel
            self.assertEqual(speech.state, 'speaking')
            media = panel.playback.media
            privacy.inactive = True
            enforce_privacy(app)
            self.assertEqual(speech.state, 'stopped')
            self.assertFalse(panel.session.text or speech.queue.prepared)
            self.assertTrue(media.closed)
            self.assertFalse(panel.playback.command('play'))
        self.exercise(fixture)

    def test_timer_and_interruption_keep_the_resume_position(self):
        async def fixture(speech, record, library, app, privacy):
            app.preferences.save(playlist_speech_when_locked='true')
            speech.play(record.id)
            await self.idle(speech)
            panel = speech.panel
            media = panel.playback.media
            panel.session.progress(panel.session.token, 7, 13)
            position = speech.queue.position
            self.assertGreater(position, 0)
            self.assertTrue(panel.playback.command('interrupt'))
            self.assertEqual(speech.state, 'paused')
            self.assertEqual(speech.queue.position, position)
            self.assertTrue(panel.playback.command('play'))
            self.assertEqual(speech.state, 'speaking')
            panel.timer_expired()
            self.assertEqual(speech.state, 'paused')
            self.assertIn('Timer finished', panel.status.text)
            self.assertIs(panel.playback.media, media)
            privacy.captured = True
            enforce_privacy(app)
            self.assertEqual(speech.state, 'stopped')
            self.assertTrue(media.closed)
        self.exercise(fixture)
