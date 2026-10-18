"""Read-aloud presentation leaves document layout intact and uses saved voices."""
import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import toga
from test_markdown_speech import Engine
import test_obsidian
import unittest


class SpeechOverlayTests(unittest.TestCase):
    setUp = test_obsidian.ObsidianTests.setUp
    tearDown = test_obsidian.ObsidianTests.tearDown
    run_async = test_obsidian.ObsidianTests.run_async

    def test_overlay_preserves_document_children_and_uses_saved_voice(self):
        from logisticsmobile.markdown_speech import MarkdownSpeech
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
                self.assertEqual(list(container.children), [web])
                self.assertIsNone(panel.parent)
                self.assertFalse(hasattr(panel, 'voice_choice'))
                self.assertEqual(panel.voice, 'Another voice')
                compact_height = panel.overlay_height
                self.assertLess(compact_height, 180)
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
                panel.speed_choice.value = '1.5'
                self.assertEqual(panel.engine.calls[-1][2], 1.5)
                panel.session.pause()
                calls = len(panel.engine.calls)
                panel.speed_choice.value = '2'
                self.assertEqual(len(panel.engine.calls), calls)
                await panel.toggle_playback()
                self.assertEqual(panel.engine.calls[-1][2], 2)
                token = panel.session.token
                close_button = panel.play_button.parent.children[-1]
                close_button.on_press()
                self.assertIsNone(panel.overlay)
                self.assertFalse(panel.closed)
                self.assertEqual(panel.session.state, 'speaking')
                speech.show()
                self.assertIs(speech.panel, panel)
                self.assertEqual(panel.session.token, token)
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

    def test_settings_load_and_persist_voice_then_release_engine(self):
        from logisticsmobile.preferences import Preferences
        from logisticsmobile.settings_ui import speech_voice_setting
        class Voices(Engine):
            voices = {'Offline': None, 'Another voice': None}
        engine = Voices(self.app.loop)
        with patch('features.books.mobile.speech_native.NativeSpeech', return_value=engine):
            box = speech_voice_setting(self.app)
            button = box.children[2]
            button.on_press()
            self.run_async(asyncio.sleep(.01))
        self.assertTrue(engine.closed)
        self.app.speech_voice_choice.value = 'Another voice'
        self.assertEqual(Preferences(self.app.private_root).values['speech_voice'], 'Another voice')
        self.app.speech_voice_choice.value = 'System default'
        self.assertEqual(Preferences(self.app.private_root).values['speech_voice'], '')
