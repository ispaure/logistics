"""Read-aloud presentation leaves document layout intact and uses saved voices."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import toga
from mobile_build.tests.editing.test_markdown_speech import Engine
from mobile_build.tests.support import notes as fixtures
import unittest


class SpeechOverlayTests(unittest.TestCase):
    def test_mobile_dash_speech_and_cursor_keep_original_passage_offsets(self):
        from features.books.mobile.speech_view import ReadAloudPanel
        from unittest.mock import Mock
        source_text = '😀 Sumire—Never again'
        async def source():
            return SimpleNamespace(text=source_text), 0, None
        async def exercise():
            ranges = Mock()
            panel = ReadAloudPanel(loop=self.app.loop, source=source, on_range=ranges,
                close=lambda *args: None, engine=Engine(self.app.loop), app=self.app)
            try:
                await panel.ready_task
                await panel.play()
                self.assertEqual(panel.engine.calls[-1][0], '😀 Sumire — Never again')
                panel.engine.progress(panel.session.token, 12, 17)
                self.assertEqual(ranges.call_args.args, (10, 15))
                self.assertEqual(panel.session.text, source_text)
            finally:
                panel.dispose()
            self.assertIsNone(panel.session.spoken)
            self.assertEqual(panel.session.text, '')
        self.run_async(exercise())

    setUp = fixtures.set_up_vault
    run_async = fixtures.run_async

    def test_old_source_success_or_error_cannot_publish_into_refreshed_session(self):
        from features.books.mobile.speech_view import ReadAloudPanel
        class Unavailable(Engine):
            backend, ready, error = 'toga_iOS.widgets.webview', False, 'No installed voice.'
        async def exercise():
            for fail in (False, True):
                release = asyncio.Event()
                async def source():
                    await release.wait()
                    if fail:
                        raise ValueError('Old source failed')
                    return SimpleNamespace(text='Old passage', language='en'), 0, None
                first, refreshed = Unavailable(self.app.loop), Engine(self.app.loop)
                with patch('features.books.mobile.speech_view.NativeSpeech', return_value=refreshed):
                    panel = ReadAloudPanel(loop=self.app.loop, source=source, on_range=lambda *a:None,
                        close=lambda *a:None, engine=first, app=self.app)
                    old = panel.session
                    pending = asyncio.create_task(panel.play())
                    try:
                        await asyncio.sleep(0)
                        await panel.ready_task  # Actual iOS refresh replaces generation-zero session.
                        self.assertIsNot(panel.session, old)
                        status = panel.status.text
                        release.set()
                        await pending
                        with self.subTest(source_error=fail):
                            self.assertEqual(refreshed.calls, [])
                            self.assertEqual(panel.status.text, status)
                            self.assertEqual(panel.session.state, 'stopped')
                    finally:
                        release.set()
                        await pending
                        panel.dispose()
        self.run_async(exercise())

    def test_old_language_worker_cannot_publish_into_refreshed_session(self):
        from features.books.mobile.speech_view import ReadAloudPanel
        from threading import Event
        class Unavailable(Engine):
            backend, ready, error = 'toga_iOS.widgets.webview', False, 'No installed voice.'
        started, release = Event(), Event()
        def language(*args):
            started.set()
            if not release.wait(3):
                raise TimeoutError('Language fixture not released')
            return 'en'
        async def source():
            return SimpleNamespace(text='Old passage', language='en'), 0, None
        async def exercise():
            first, refreshed = Unavailable(self.app.loop), Engine(self.app.loop)
            with patch('features.books.mobile.speech_view.NativeSpeech', return_value=refreshed), \
                    patch('features.books.mobile.speech_view.passage_language', side_effect=language):
                panel = ReadAloudPanel(loop=self.app.loop, source=source, on_range=lambda *a:None,
                    close=lambda *a:None, engine=first, app=self.app)
                pending = asyncio.create_task(panel.play())
                try:
                    self.assertTrue(await asyncio.to_thread(started.wait, 2))
                    await panel.ready_task
                    release.set()
                    await pending
                    self.assertEqual(refreshed.calls, [])
                    self.assertEqual(panel.session.state, 'stopped')
                finally:
                    release.set()
                    await pending
                    panel.dispose()
        self.run_async(exercise())

    def test_old_continuation_cannot_restart_refreshed_session(self):
        from features.books.mobile.speech_view import ReadAloudPanel
        from unittest.mock import AsyncMock
        class Unavailable(Engine):
            backend, ready, error = 'toga_iOS.widgets.webview', False, 'No installed voice.'
        async def exercise():
            release = asyncio.Event()
            async def next_chapter(panel):
                await release.wait()
                return True
            with patch('features.books.mobile.speech_view.NativeSpeech', return_value=Engine(self.app.loop)):
                panel = ReadAloudPanel(loop=self.app.loop, source=lambda:None, on_range=lambda *a:None,
                    close=lambda *a:None, engine=Unavailable(self.app.loop), app=self.app, next_chapter=next_chapter)
                panel.continue_book = True
                panel.playback.can_start = lambda:True
                panel.play = AsyncMock()
                panel.finished()
                pending = panel.continuation_task
                try:
                    await asyncio.sleep(0)
                    await panel.ready_task
                    release.set()
                    await pending
                    panel.play.assert_not_awaited()
                finally:
                    release.set()
                    await pending
                    panel.dispose()
        self.run_async(exercise())

    def test_ios_empty_voice_discovery_refreshes_and_can_play_saved_voice(self):
        from features.books.mobile.speech_view import ReadAloudPanel
        class Unavailable(Engine):
            backend, ready, error = 'toga_iOS.widgets.webview', False, 'No installed voice.'
            voices, default_voice = {}, ''
        class Voices(Engine):
            voices = {'Offline': None, 'Saved voice': None}
        self.app.preferences.save(speech_voice='Saved voice')
        async def source():
            return SimpleNamespace(text='A short passage.', language='en'), 0, None
        async def exercise():
            first, refreshed = Unavailable(self.app.loop), Voices(self.app.loop)
            with patch('features.books.mobile.speech_view.NativeSpeech', return_value=refreshed) as factory:
                panel = ReadAloudPanel(loop=self.app.loop, source=source, on_range=lambda *a: None,
                    close=lambda *a: None, engine=first, app=self.app)
                try:
                    await panel.ready_task
                    self.assertTrue(first.closed)
                    self.assertTrue(panel.play_button.enabled)
                    self.assertEqual(panel.voice, 'Saved voice')
                    await panel.play()
                    self.assertEqual(refreshed.calls[-1][1], 'Saved voice')
                    self.assertEqual(panel.session.state, 'speaking')
                    panel.hide()
                    panel.show_over(toga.Box())
                    factory.assert_called_once()
                finally:
                    panel.dispose()
                self.assertTrue(refreshed.closed)
        self.run_async(exercise())

    def test_ios_refresh_is_bounded_and_failed_panel_retries_on_reopening(self):
        from features.books.mobile.speech_view import ReadAloudPanel
        class Unavailable(Engine):
            backend, ready, error = 'toga_iOS.widgets.webview', False, 'No installed voice.'
            voices, default_voice = {}, ''
        async def exercise():
            first, second, recovered = Unavailable(self.app.loop), Unavailable(self.app.loop), Engine(self.app.loop)
            with patch('features.books.mobile.speech_view.NativeSpeech', side_effect=[second, recovered]) as factory:
                panel = ReadAloudPanel(loop=self.app.loop, source=lambda: None, on_range=lambda *a: None,
                    close=lambda *a: None, engine=first, app=self.app)
                try:
                    await panel.ready_task
                    factory.assert_called_once()
                    self.assertFalse(panel.play_button.enabled)
                    self.assertIn('No installed voice', panel.status.text)
                    panel.show_over(toga.Box())
                    retry = panel.ready_task
                    panel.hide()
                    panel.show_over(toga.Box())
                    self.assertIs(panel.ready_task, retry)
                    await retry
                    self.assertTrue(second.closed)
                    self.assertTrue(panel.play_button.enabled)
                    self.assertEqual(factory.call_count, 2)
                finally:
                    panel.dispose()
        self.run_async(exercise())

    def test_closing_during_ios_refresh_does_not_create_another_engine(self):
        from features.books.mobile.speech_view import ReadAloudPanel
        class Unavailable(Engine):
            backend, ready, error = 'toga_iOS.widgets.webview', False, 'No installed voice.'
        async def exercise():
            first = Unavailable(self.app.loop)
            with patch('features.books.mobile.speech_view.NativeSpeech') as factory:
                panel = ReadAloudPanel(loop=self.app.loop, source=lambda: None, on_range=lambda *a: None,
                    close=lambda *a: None, engine=first, app=self.app)
                await asyncio.sleep(0)
                self.assertIn('Refreshing', panel.status.text)
                panel.dispose()
                with self.assertRaises(asyncio.CancelledError):
                    await panel.ready_task
                factory.assert_not_called()
                self.assertTrue(first.closed)
        self.run_async(exercise())

    def test_automatic_voice_follows_each_passage_and_reports_missing_language(self):
        from commonUtils.ui.native.speech import NativeSpeech
        from features.books.mobile.speech_view import ReadAloudPanel
        class Voices(Engine):
            voices = {'en-US · English': None, 'fr-FR · French': None}
            default_voice = 'en-US · English'
            voice_for_language = NativeSpeech.voice_for_language
        text = ['Le petit garçon ouvre la porte de la maison. Il regarde le jardin et cherche son livre sur la table.']
        async def source():
            return SimpleNamespace(text=text[0]), 0, None
        async def exercise():
            panel = ReadAloudPanel(loop=self.app.loop, source=source, on_range=lambda *args: None,
                                   close=lambda *args: None, engine=Voices(self.app.loop), app=self.app)
            try:
                await panel.ready_task
                await panel.play()
                self.assertEqual(panel.engine.calls[-1][1], 'fr-FR · French')
                panel.session.stop()
                text[0] = 'The little boy opened the door of the house. He looked into the garden and searched for the book on the table.'
                await panel.play()
                self.assertEqual(panel.engine.calls[-1][1], 'en-US · English')
                panel.session.stop()
                text[0] = 'Der kleine Junge öffnete die Tür des Hauses. Er schaute in den Garten und suchte das Buch auf dem Tisch.'
                calls = len(panel.engine.calls)
                await panel.play()
                self.assertEqual(len(panel.engine.calls), calls)
                self.assertIn('No installed voice for de', panel.status.text.replace('\n', ' '))
            finally:
                panel.dispose()
        self.run_async(exercise())

    def test_unavailable_saved_voice_plays_system_default_even_without_language_match(self):
        from commonUtils.ui.native.speech import NativeSpeech
        from features.books.mobile.speech_view import ReadAloudPanel
        class Voices(Engine):
            voices = {'en-US · English': None}
            default_voice = 'en-US · English'
            voice_for_language = NativeSpeech.voice_for_language
        self.app.preferences.save(speech_voice='Removed German voice')
        async def source():
            return SimpleNamespace(text='Ein deutsches Buch.', language='de'), 0, None
        async def exercise():
            panel = ReadAloudPanel(loop=self.app.loop, source=source, on_range=lambda *args: None,
                close=lambda *args: None, engine=Voices(self.app.loop), app=self.app)
            try:
                await panel.ready_task
                self.assertTrue(panel.missing_saved_voice)
                await panel.play()
                self.assertEqual(panel.engine.calls[-1][1], 'en-US · English')
            finally:
                panel.dispose()
        self.run_async(exercise())

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

    def test_voice_discovery_failure_closes_engine_and_keeps_default_selectable(self):
        from mobile.settings.speech import speech_voice_setting
        class Unavailable(Engine):
            ready, error = False, 'Install an offline system voice.'
        engine = Unavailable(self.app.loop)
        with patch('commonUtils.ui.native.speech.NativeSpeech', return_value=engine) as factory:
            box = speech_voice_setting(self.app)
            task = self.app.speech_voice_load_task
            self.assertIs(box._settings_on_open(), task)
            self.run_async(task)
            factory.assert_called_once()
        self.assertTrue(engine.closed)
        self.assertEqual(self.app.speech_voice_choice.value, 'System default')
        self.assertEqual(box.children[-1].text, engine.error)
        self.assertTrue(box.children[2].enabled)

    def test_settings_load_and_persist_voice_then_release_engine(self):
        from mobile.preferences import Preferences
        from mobile.settings.speech import speech_voice_setting
        class Voices(Engine):
            voices = {'Offline': None, 'Another voice': None}
        engine = Voices(self.app.loop)
        with patch('commonUtils.ui.native.speech.NativeSpeech', return_value=engine):
            box = speech_voice_setting(self.app)
            self.assertEqual(box.children[2].text, 'Refresh voices')
            self.run_async(self.app.speech_voice_load_task)
        self.assertTrue(engine.closed)
        self.app.speech_voice_choice.value = 'Another voice'
        self.assertEqual(Preferences(self.app.private_root).values['speech_voice'], 'Another voice')
        self.app.speech_voice_choice.value = 'System default'
        self.assertEqual(Preferences(self.app.private_root).values['speech_voice'], '')
