"""Lock-screen command routing, credential policy and process ownership."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest

from features.books.mobile.media_controls import SpeechPlayback, enforce_privacy, current_panel, settings_changed
from features.books.mobile.speech import SpeechSession
from features.rclone.mobile.session_privacy import ResumePassword
from mobile.preferences import Preferences


class Engine:
    ready, error = True, ''
    def __init__(self): self.calls = []
    def speak(self, *args): self.calls.append(args)
    def stop(self): pass
    def close(self): pass


class Media:
    def __init__(self, loop, command):
        self.command, self.states, self.closed = command, [], False
    def update(self, state, *, timer_text=''):
        self.states.append(state)
        self.timer_text = timer_text
    def update_timer(self, text): self.timer_text = text
    def update_content(self, title): self.title = title
    def close(self): self.closed = True


class SpeechMediaTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.loop = asyncio.new_event_loop()
        self.addCleanup(self.loop.close)
        self.app = NS(loop=self.loop, preferences=Preferences(Path(self.temp.name)), screen_privacy=NS(inactive=False))

    def player(self, gate=None, valid=lambda: True, title=''):
        panel = NS(document_title=lambda: title)
        playback = SpeechPlayback(panel, self.app, gate=lambda: gate, valid=valid, factory=Media)
        panel.session = SpeechSession(Engine(), on_range=lambda *a: None, on_state=lambda state, msg: playback.changed(state))
        panel.session.can_speak = playback.can_start
        self.addCleanup(playback.dispose)
        panel.session.play(' '.join('word'+str(i) for i in range(400)))
        return panel, playback

    def test_system_metadata_has_title_and_timer_but_never_document_passages(self):
        panel, owner = self.player(title='/folder/Notes😀.md')
        media = owner.media
        self.assertEqual(media.title, 'Notes😀.md')
        self.assertFalse(hasattr(media, 'excerpt'))
        panel.session.skip(15)
        self.assertFalse(hasattr(media, 'excerpt'))
        owner.timer_changed('Time remaining: 15:00')
        self.assertEqual(media.timer_text, 'Time remaining: 15:00')
        self.assertFalse(hasattr(media, 'excerpt'))
        panel.session.pause()
        self.assertEqual(media.states[-1], 'paused')
        owner.command('stop')
        self.assertTrue(media.closed)
        self.assertIsNone(owner.media)

        self.app.preferences.save(session_speech_when_locked='true')
        private, private_owner = self.player(ResumePassword('secret'), title='Secret.md')
        self.assertEqual(private_owner.media.title, 'Read aloud')
        self.assertFalse(hasattr(private_owner.media, 'excerpt'))
        private_owner.timer_changed('Time remaining: 15:00')
        self.assertEqual(private_owner.media.timer_text, 'Time remaining: 15:00')
        private.session.skip(15)
        self.assertFalse(hasattr(private_owner.media, 'excerpt'))

    def test_regular_speech_commands_ownership_and_teardown(self):
        panel, owner = self.player()
        media = owner.media
        self.assertIs(current_panel(self.app), panel)
        self.app.screen_privacy.inactive = True
        enforce_privacy(self.app)
        self.assertEqual(panel.session.state, 'speaking')
        self.assertTrue(owner.command('pause'))
        self.assertEqual(panel.session.state, 'paused')
        owner.command('forward')
        self.assertGreater(panel.session.ranges[0][1], 0)
        owner.command('back')
        owner.command('play')
        self.assertEqual(panel.session.state, 'speaking')
        other, second = self.player()
        self.assertTrue(media.closed)
        self.assertEqual(panel.session.state, 'stopped')
        second.command('stop')
        self.assertIsNone(second.media)
        self.assertEqual(other.session.ranges, [])
        self.assertFalse(second.command('play'))

    def test_session_default_off_and_remembered_opt_in_keeps_gate_locked(self):
        gate = ResumePassword('temporary')
        panel, owner = self.player(gate)
        self.assertIsNone(owner.media)
        self.assertEqual(panel.session.state, 'speaking')
        self.app.screen_privacy.inactive = True
        gate.lock()
        enforce_privacy(self.app)
        self.assertEqual(panel.session.state, 'stopped')
        self.assertFalse(panel.session.text or panel.session.ranges)
        self.assertFalse(owner.can_start())
        self.app.preferences.save(session_speech_when_locked='true')
        self.assertEqual(Preferences(self.app.preferences.path.parent).values['session_speech_when_locked'], 'true')
        panel.session.play(' '.join('word'+str(i) for i in range(400)))
        self.assertTrue(owner.can_start())
        self.assertTrue(gate.locked)
        self.assertIsNotNone(owner.media)
        owner.command('pause');owner.command('forward');owner.command('play')
        self.assertEqual(panel.session.state, 'speaking')
        self.app.preferences.save(session_speech_when_locked='false')
        settings_changed(self.app)
        self.assertIsNone(owner.media)
        self.assertEqual(panel.session.state, 'stopped')
        self.assertEqual(panel.session.words, [])
        self.assertTrue(gate.locked)

    def test_credential_revocation_defeats_opt_in_and_stale_commands(self):
        valid = [True]
        self.app.preferences.save(session_speech_when_locked='true')
        panel, owner = self.player(ResumePassword('temporary'), valid=lambda: valid[0])
        media = owner.media
        valid[0] = False
        self.assertFalse(media.command('forward'))
        self.assertTrue(media.closed)
        self.assertEqual(panel.session.state, 'stopped')
        self.assertFalse(panel.session.text or panel.session.words)


    def test_revocation_is_checked_before_the_next_native_utterance(self):
        valid = [True]
        panel, owner = self.player(valid=lambda: valid[0])
        before = len(panel.session.engine.calls)
        token = panel.session.token
        valid[0] = False
        panel.session.completed(token)
        self.assertEqual(panel.session.state, 'stopped')
        self.assertEqual(len(panel.session.engine.calls), before)
        self.assertFalse(panel.session.text or panel.session.words)



class SpeechPrivacyIntegrationTests(unittest.TestCase):
    def setUp(self):
        import test_obsidian
        test_obsidian.ObsidianTests.setUp(self)
    def tearDown(self):
        import test_obsidian
        test_obsidian.ObsidianTests.tearDown(self)

    def test_private_markdown_background_opt_in_trim_and_revocation(self):
        import json
        from unittest.mock import AsyncMock, patch
        from commonUtils.runtime.local_files import LocalFiles
        from features.text_editor.resources import LocalTextCopies
        from test_markdown_speech import Engine as SpeechEngine
        class Copies(LocalTextCopies):
            encrypted = True
        async def exercise():
            (self.root / 'Private.md').write_text('# Private')
            await self.app.open_crypt(copies=Copies(LocalFiles(self.root)), key='Private.md')
            owner = self.app.private_sessions.active
            owner.privacy_gate = ResumePassword('temporary')
            with patch('features.books.mobile.speech_view.NativeSpeech', SpeechEngine), patch(
                    'features.books.mobile.media_controls.native_media', Media):
                owner.markdown_speech.show()
                panel = owner.markdown_speech.panel
                await panel.ready_task
                with patch.object(owner.crypt_preview, 'evaluate_javascript', AsyncMock(return_value=json.dumps('Private words. '*100))):
                    await panel.play()
                    self.assertIsNone(panel.playback.media)
                    self.app.screen_privacy.conceal()
                    self.assertTrue(owner.privacy_gate.locked)
                    self.assertEqual(panel.session.state, 'stopped')
                    self.app.preferences.save(session_speech_when_locked='true')
                    await panel.play()
                media = panel.playback.media
                self.assertIsNotNone(media)
                self.app.release_disposable_resources()
                self.assertEqual(panel.session.state, 'speaking')
                self.assertIn(owner.crypt_preview, owner.crypt_content.children)
                owner.credential_generation = -999
                self.assertFalse(media.command('forward'))
                self.assertTrue(media.closed)
                self.assertFalse(panel.session.text or panel.session.words)
                owner.markdown_speech.close()
        self.app.loop.run_until_complete(exercise())

    def test_late_dom_read_cannot_start_session_speech_after_lock(self):
        import json
        from unittest.mock import AsyncMock, patch
        from test_markdown_speech import Engine as SpeechEngine
        from mobile.markdown_speech import MarkdownSpeech
        import toga
        async def exercise():
            gate = ResumePassword('temporary')
            web = toga.WebView()
            speech = MarkdownSpeech(self.app, web, toga.Box(), privacy_gate=lambda: gate)
            with patch('features.books.mobile.speech_view.NativeSpeech', SpeechEngine):
                speech.show();panel = speech.panel
                await panel.ready_task
                pending = self.app.loop.create_future()
                async def delayed(*args): return await pending
                with patch.object(web, 'evaluate_javascript', AsyncMock(side_effect=delayed)):
                    task = self.app.loop.create_task(panel.play())
                    await asyncio.sleep(0)
                    gate.lock();self.app.screen_privacy.inactive = True
                    enforce_privacy(self.app)
                    pending.set_result(json.dumps('Late private words'))
                    await task
                self.assertEqual(panel.engine.calls, [])
                self.assertEqual(panel.session.state, 'stopped')
                speech.close()
        self.app.loop.run_until_complete(exercise())
