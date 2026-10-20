"""Portable speech ownership, UTF-16 utterances and safe reader styling."""

import unittest
from features.books.mobile.speech import utterances, SpeechSession
from features.books.mobile.typography import css, options
from features.books.locations import ChapterText, utf16_length


class Engine:
    ready = True
    error = ""

    def __init__(self):
        self.calls, self.closed, self.stops = [], False, 0

    def speak(self, *args):
        self.calls.append(args)

    def stop(self):
        self.stops += 1

    def close(self):
        self.closed = True


class SpeechTests(unittest.TestCase):
    def test_speed_changes_restart_current_word_and_preserve_pause_and_selection(self):
        engine = Engine()
        session = SpeechSession(engine, on_range=lambda *args: None, on_state=lambda *args: None)
        self.addCleanup(session.dispose)
        session.play('😀 One two. Secret tail.', 0, 11, voice='local')
        old = session.token
        session.progress(old, 7, 10)
        session.set_speed(1.5)
        self.assertEqual(engine.calls[-1][:3], ('two.', 'local', 1.5))
        self.assertEqual(session.ranges[-1][2], 11)
        session.completed(old)
        session.failed(old)
        self.assertEqual(session.state, 'speaking')
        session.pause()
        calls = len(engine.calls)
        session.set_speed(.75)
        self.assertEqual(session.state, 'paused')
        self.assertEqual(len(engine.calls), calls)
        session.resume()
        self.assertEqual(engine.calls[-1][:3], ('two.', 'local', .75))

    def test_skip_clears_old_word_before_native_stop_and_rejects_its_callbacks(self):
        engine = Engine()
        ranges = []
        session = SpeechSession(engine, on_range=lambda *value: ranges.append(value), on_state=lambda *args: None)
        self.addCleanup(session.dispose)
        session.play(' '.join(f'word{i}' for i in range(200)))
        old = session.token
        session.progress(old, 0, 5)
        observed = []
        def native_stop():
            observed.append(ranges[-1])
            session.progress(old, 6, 11)
            session.completed(old)
        engine.stop = native_stop
        session.skip(15)
        self.assertEqual(observed[-1], (-1, -1))
        self.assertEqual(ranges[-1], (-1, -1))
        session.progress(session.token, 0, 6)
        self.assertGreater(ranges[-1][0], 0)
        session.pause()
        session.skip(-15)
        self.assertEqual(session.state, 'paused')
        self.assertGreaterEqual(ranges[-1][0], 0)

    def test_native_word_offsets_selection_and_stale_events(self):
        engine = Engine()
        ranges = []
        session = SpeechSession(engine, on_range=lambda *r: ranges.append(r), on_state=lambda *s: None)
        session.play('Skip. 😀 One two.', 6, voice='local')
        token = session.token
        engine.started(token)
        self.assertEqual(ranges[-1], (6, 8))
        engine.progress(token, 3, 6)
        self.assertEqual(ranges[-1], (9, 12))
        count = len(ranges)
        engine.progress(token, -1, 100)
        self.assertEqual(len(ranges), count)
        session.pause()
        engine.progress(token, 7, 11)
        engine.started(token)
        self.assertEqual(len(ranges), count)
        session.resume()
        engine.progress(token, 0, 2)
        self.assertEqual(len(ranges), count)
        engine.progress(session.token, 0, 3)
        self.assertEqual(ranges[-1], (9, 12))
        session.stop()
        self.assertEqual(ranges[-1], (-1, -1))
        engine.progress(session.token, 0, 2)
        self.assertEqual(ranges[-1], (-1, -1))
        session.dispose()

    def test_estimated_words_wait_for_audio_start_and_yield_to_native_progress(self):
        import asyncio
        engine = Engine()
        engine.loop = asyncio.new_event_loop()
        self.addCleanup(engine.loop.close)
        ranges = []
        session = SpeechSession(engine, on_range=lambda *r: ranges.append(r), on_state=lambda *s: None)
        self.addCleanup(session.dispose)
        session.play('One two three.', voice='local')
        self.assertEqual(ranges, [(-1, -1)])
        engine.started(session.token)
        self.assertEqual(ranges[-1], (0, 3))
        timer = session.word_timer
        self.assertIsNotNone(timer)
        engine.progress(session.token, 4, 7)
        self.assertTrue(timer.cancelled())
        session.estimated_word(session.token, 2)
        self.assertEqual(ranges[-1], (4, 7))

    def test_unicode_selection_chunks_and_block_boundaries(self):
        chapter = ChapterText(
            "<html><body><h1>😀 Title</h1><p>Straße. Next sentence.</p></body></html>"
        )
        chunks = list(utterances(chapter.text, breaks=chapter.breaks, limit=12))
        self.assertEqual(
            "".join(text for text, _, _ in chunks).replace(" ", ""),
            chapter.text.replace(" ", ""),
        )
        self.assertEqual(chunks[0], ("😀 Title", 0, 8))
        self.assertTrue(
            all(
                utf16_length(text) <= 12 and end - start == utf16_length(text)
                for text, start, end in chunks
            )
        )
        self.assertEqual(list(utterances(chapter.text, 8, 15))[0], ("Straße.", 8, 15))

    def test_pause_resumes_current_word_and_ignores_old_native_completion(self):
        engine = Engine()
        session = SpeechSession(engine, on_range=lambda *args: None, on_state=lambda *args: None)
        session.play('One two three four five.', voice='local', speed=1.25)
        old = session.token
        session.progress(old, 8, 13)
        session.pause()
        session.completed(old)
        session.resume()
        self.assertEqual(session.ranges[session.index], ('three four five.', 8, 24))
        session.pause()
        session.resume()
        self.assertEqual(session.ranges[session.index][1], 8)
        self.assertEqual(session.speed, 1.25)

    def test_pause_repeat_sentence_stale_callbacks_completion_and_disposal(self):
        engine = Engine()
        ranges, states = [], []
        session = SpeechSession(
            engine,
            on_range=lambda *r: ranges.append(r),
            on_state=lambda *s: states.append(s),
        )
        session.play("One. Two.", voice="local", speed=1.25)
        first = session.token
        session.pause()
        session.resume()
        session.completed(first)
        self.assertEqual(session.index, 0)
        session.completed(session.token)
        self.assertEqual(session.index, 1)
        session.completed(session.token)
        self.assertEqual(session.state, "stopped")
        self.assertEqual(session.ranges, [])
        session.dispose()
        session.play("Must not speak")
        self.assertTrue(engine.closed)
        self.assertEqual(len(engine.calls), 3)

    def test_time_skip_retains_selection_speed_pause_and_invalidates_callbacks(self):
        from unittest.mock import patch
        text = 'Prefix 😀 ' + ' '.join('word' + str(i) for i in range(180)) + ' secret tail'
        start = utf16_length('Prefix 😀 ')
        end = utf16_length(text.removesuffix(' secret tail'))
        engine = Engine()
        session = SpeechSession(engine, on_range=lambda *r: None, on_state=lambda *s: None)
        with patch('features.books.mobile.speech.monotonic', return_value=100):
            session.play(text, start, end, voice='local', speed=2)
            old_token = session.token
            session.skip(15)
            # 180 words/minute at 2x: about 90 words in 15 seconds.
            expected = utf16_length('Prefix 😀 ' + ' '.join('word' + str(i) for i in range(90)) + ' ')
            self.assertEqual(session.ranges[0][1], expected)
            self.assertEqual(session.ranges[-1][2], end)
            session.completed(old_token)
            self.assertEqual(session.index, 0)
            session.pause()
            calls = len(engine.calls)
            session.skip(-15)
            self.assertEqual(session.state, 'paused')
            self.assertEqual(session.ranges[0][1], start)
            self.assertEqual(len(engine.calls), calls)
            session.skip(-15)
            self.assertEqual(session.ranges[0][1], start)
            session.resume()
            session.skip(999)
            self.assertLess(session.ranges[0][1], end)
            self.assertEqual(session.ranges[-1][2], end)
            session.dispose()
            session.skip(15)
            self.assertFalse(session.text or session.words or session.ranges)

    def test_typography_is_offline_bounded_and_theme_complete(self):
        for theme in ["system", "light", "dark", "sepia", "slate"]:
            result = css(
                20,
                24,
                theme,
                font_family="Georgia",
                line_spacing=200,
                reading_width="640",
            )
            self.assertIn('font-family:"Georgia",sans-serif', result)
            self.assertIn("line-height:2.0", result)
            self.assertIn("max-width:640px", result)
        for family in ["url(https://evil.invalid)", "x; color:red", "<script>", 'x"']:
            with self.assertRaises(ValueError):
                css(16, 16, "light", font_family=family)
        self.assertEqual(options({})["line_spacing"], 150)
