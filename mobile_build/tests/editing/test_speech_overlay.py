"""Read-aloud presentation leaves document layout intact and uses saved voices."""
import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import toga
from mobile_build.tests.editing.test_markdown_speech import Engine
import mobile_build.tests.documents.test_obsidian as test_obsidian
import unittest


class SpeechOverlayTests(unittest.TestCase):
    setUp = test_obsidian.ObsidianTests.setUp
    tearDown = test_obsidian.ObsidianTests.tearDown
    run_async = test_obsidian.ObsidianTests.run_async

    def test_overlay_preserves_document_children_and_uses_saved_voice(self):
        from mobile.markdown_speech import MarkdownSpeech
        class Voices(Engine):
            voices = {'Offline': None, 'Another voice': None}
        self.app.preferences.save(speech_voice='Another voice')
        web = toga.WebView()
        container = toga.Box(children=[web])
        speech = MarkdownSpeech(self.app, web, container)

        async def exercise():
            with patch('features.books.mobile.speech_view.NativeSpeech', Voices):
                speech.show()
                panel = speech.panel
                await panel.ready_task
                for label in (panel.speed_minimum, panel.speed_maximum, *panel.speed_track.children[1].children):
                    if isinstance(label, toga.Label):
                        self.assertFalse(label._impl._surface_eink_outlined)
                self.assertEqual(list(container.children), [web])
                self.assertIsNone(panel.parent)
                self.assertFalse(hasattr(panel, 'voice_choice'))
                self.assertEqual(panel.voice, 'Another voice')
                compact_height = panel.overlay_height
                self.assertLess(compact_height, 280)
                with patch.object(panel.overlay, 'reposition') as reposition:
                    message = 'Could not read this passage. Try reopening the document.'
                    panel.set_status(message)
                    self.assertEqual(panel.status.text.replace('\n', ' '), message)
                    self.assertGreater(panel.overlay_height, compact_height)
                    panel.set_status('Paused')
                    self.assertEqual(panel.overlay_height, compact_height)
                    self.assertEqual(reposition.call_count, 2)
                async def source():
                    return SimpleNamespace(text='A spoken passage.'), 0, None
                panel.source = source
                await panel.play()
                self.assertEqual(panel.session.voice, 'Another voice')
                panel.speed_choice.value = 1.5
                self.assertEqual(panel.engine.calls[-1][2], 1.5)
                panel.session.pause()
                calls = len(panel.engine.calls)
                panel.speed_choice.value = 2
                self.assertEqual(len(panel.engine.calls), calls)
                await panel.toggle_playback()
                self.assertEqual(panel.engine.calls[-1][2], 2)
                token = panel.session.token
                self.assertEqual([button.control_icon for button in panel.play_button.parent.children],
                    ['skip_back', 'pause', 'skip_forward', 'stop'])
                panel.hide()
                self.assertIsNone(panel.overlay)
                self.assertFalse(panel.closed)
                self.assertEqual(panel.session.state, 'speaking')
                speech.show()
                self.assertIs(speech.panel, panel)
                self.assertEqual(panel.session.token, token)
                speech.show()  # The same speaker control dismisses without stopping playback.
                self.assertIsNone(panel.overlay)
                self.assertEqual(panel.session.token, token)
                speech.show()
                self.assertIsNotNone(panel.overlay)
                overlay = panel.overlay
                speech.close()
                self.assertTrue(panel.closed)
                self.assertIsNone(panel.overlay)
                self.assertIsNone(overlay.container)
                self.assertEqual(list(container.children), [web])
                self.app.preferences.save(speech_voice='Removed voice')
                speech.show()
                await speech.panel.ready_task
                self.assertEqual(speech.panel.voice, 'Offline')
                speech.close()
        self.run_async(exercise())

    def test_speed_slider_snaps_and_shows_percent_limits(self):
        from features.books.mobile.speech_view import ReadAloudPanel
        async def exercise():
            panel = ReadAloudPanel(loop=self.app.loop, source=lambda: None, on_range=lambda *a: None,
                close=lambda: None, engine=Engine(self.app.loop))
            try:
                await panel.ready_task
                self.assertIsInstance(panel.speed_choice, toga.Slider)
                self.assertEqual(panel.speed_choice.tick_count, 7)
                self.assertEqual((panel.speed_minimum.text, panel.speed_maximum.text), ('50%', '200%'))
                for requested, expected in ((.1, .5), (.63, .75), (1.12, 1), (1.38, 1.5), (3, 2)):
                    panel.speed_choice.value = requested
                    self.assertEqual(panel.speed_choice.value, expected)
                    self.assertEqual(panel.session.speed, expected)
                    self.assertEqual(panel.speed_value.text, f'{expected * 100:.0f}%')
                self.assertEqual(panel.reset_timer_button.control_icon, 'reset')
                self.assertEqual(panel.reset_timer_button.accessible_name, 'Reset timer')
            finally:
                panel.dispose()
        self.run_async(exercise())

    def test_timer_follows_playback_and_survives_hidden_controls(self):
        from features.books.mobile.speech_view import ReadAloudPanel
        from mobile_build.tests.editing.test_speech_media import Media

        async def exercise():
            async def source():
                return SimpleNamespace(text='One two. Three four.'), 0, None
            panel = ReadAloudPanel(loop=self.app.loop, source=source, on_range=lambda *a: None,
                close=lambda: None, engine=Engine(self.app.loop), app=self.app,
                document_title=lambda: '/books/Spoken.epub')
            try:
                await panel.ready_task
                now = 0
                panel.timer.clock = lambda: now
                panel.timer_choice.value = '15 min'
                self.assertEqual(panel.timer_remaining.text, 'Time remaining: 15:00')
                self.assertIsNone(panel.playback.media)
                await panel.toggle_playback()
                media = panel.playback.media
                self.assertEqual(media.title, 'Spoken.epub')
                self.assertFalse(hasattr(media, 'excerpt'))
                deadline = panel.timer.deadline
                panel.session.completed(panel.session.token)
                self.assertFalse(hasattr(media, 'excerpt'))
                self.assertEqual(panel.timer.deadline, deadline)
                self.assertEqual(media.timer_text, panel.timer_remaining.text)
                self.assertEqual(media.states[-1], 'speaking')
                now = 10
                panel.timer._cancel()
                panel.timer._tick()
                self.assertEqual(media.timer_text, 'Time remaining: 14:50')
                now = 20
                panel.playback.command('pause')
                self.assertEqual(panel.timer_remaining.text, 'Time remaining: 14:40')
                self.assertEqual(media.timer_text, panel.timer_remaining.text)
                self.assertEqual(media.states[-1], 'paused')
                now = 200
                self.assertEqual(panel.timer.remaining, 880)
                panel.reset_timer_button.on_press()
                self.assertEqual(panel.session.state, 'paused')
                self.assertEqual(panel.timer.remaining, 900)
                self.assertEqual(media.timer_text, 'Time remaining: 15:00')
                panel.playback.command('play')
                panel.hide()
                now = 1101
                panel.timer._cancel()
                panel.timer._tick()
                self.assertEqual(panel.session.state, 'paused')
                self.assertEqual(panel.timer_remaining.text, 'Time remaining: 00:00')
                self.assertEqual(media.timer_text, panel.timer_remaining.text)
                self.assertEqual(media.states[-1], 'paused')
                self.assertIn('Timer finished', panel.status.text)
                await panel.toggle_playback()
                self.assertEqual(panel.timer.remaining, 900)
                panel.timer_choice.value = 'Off'
                self.assertEqual(panel.timer_remaining.text, 'Timer off')
                self.assertEqual(media.timer_text, '')
                self.assertFalse(panel.reset_timer_button.enabled)
                self.assertEqual(panel.session.state, 'speaking')
                panel.timer_choice.value = '1 hr'
                self.assertEqual(media.timer_text, 'Time remaining: 60:00')
            finally:
                panel.dispose()
            self.assertIsNone(panel.timer.handle)
            self.assertTrue(media.closed)
        with patch('features.books.mobile.media_controls.native_media', Media):
            self.run_async(exercise())

    def test_settings_load_and_persist_voice_then_release_engine(self):
        from mobile.preferences import Preferences
        from mobile.settings.speech import speech_voice_setting
        class Voices(Engine):
            voices = {'Offline': None, 'Another voice': None}
        engine = Voices(self.app.loop)
        with patch('commonUtils.ui.native.speech.NativeSpeech', return_value=engine):
            box = speech_voice_setting(self.app)
            button = box.children[2]
            button.on_press()
            self.run_async(asyncio.sleep(.01))
        self.assertTrue(engine.closed)
        self.app.speech_voice_choice.value = 'Another voice'
        self.assertEqual(Preferences(self.app.private_root).values['speech_voice'], 'Another voice')
        self.app.speech_voice_choice.value = 'System default'
        self.assertEqual(Preferences(self.app.private_root).values['speech_voice'], '')
