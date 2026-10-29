"""Whole-book speech uses real chapter publication with a silent speech engine."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

import toga
from commonUtils.runtime.resources.documents import LocalDocuments
from features.books.mobile.speech_view import ReadAloudPanel
from mobile.app import LogisticsMobile
from services.documents.readers import PrivateReader
from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books
from mobile_build.tests.editing.test_markdown_speech import Engine


@contextmanager
def reader_app():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        LogisticsMobile.storage_root = root / 'app'
        app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        try:
            yield app, make_books(root)[0]
        finally:
            app.main_window.close()
            app.loop.close()
            LogisticsMobile.storage_root = None


async def finish_book(panel):
    for _ in range(20):
        if panel.session.state == 'speaking':
            panel.session.completed(panel.session.token)
        task = panel.continuation_task
        if task is not None:
            await task
        if panel.session.state == 'stopped' and panel.continuation_task is task and (task is None or task.done()):
            return
    raise AssertionError('Whole-book speech did not finish')


class ContinuationTests(unittest.TestCase):
    def test_empty_chapter_is_skipped_and_continuation_requires_current_audio_grant(self):
        async def exercise():
            loop = asyncio.get_running_loop()
            chapters = ['First.', '', 'Last.']
            current = [0]
            async def source():
                return SimpleNamespace(text=chapters[current[0]]), 0, None
            async def advance(panel):
                if current[0] + 1 == len(chapters):
                    return False
                current[0] += 1
                return True
            panel = ReadAloudPanel(loop=loop, source=source, on_range=Mock(), close=Mock(),
                                   engine=Engine(loop), next_chapter=advance)
            panel.playback = SimpleNamespace(request_start=Mock(return_value=True),
                can_start=Mock(return_value=True), changed=Mock(), dispose=Mock(), timer_changed=Mock())
            try:
                await panel.ready_task
                await panel.play()
                await finish_book(panel)
                self.assertEqual(current[0], 2)
                self.assertEqual([call[0] for call in panel.engine.calls], ['First.', 'Last.'])
                panel.playback.request_start.assert_called_once()
                current[0] = 0
                await panel.play()
                panel.playback.can_start.return_value = False
                panel.session.completed(panel.session.token)
                await panel.continuation_task
                self.assertEqual(current[0], 0)
                self.assertEqual(panel.session.state, 'stopped')
                panel.playback.can_start.return_value = True
                await panel.play()
                panel.timer.select(10)
                panel.timer.deadline = panel.timer.clock() - 1
                panel.session.completed(panel.session.token)
                await panel.continuation_task
                self.assertEqual(current[0], 0)
                self.assertIn('Timer finished', panel.status.text)
            finally:
                panel.dispose()
        asyncio.run(exercise())

    def test_imported_book_keeps_panel_timer_and_current_menu_across_chapters(self):
        with reader_app() as (app, epub):
            record = app.reader_manager().catalog.library_store.import_book(LocalDocuments(), epub)
            async def exercise():
                await app.open_book(record['id'])
                owner = app.readers.active
                async def source(view, chapter, offset):
                    return chapter, offset, None
                with (patch('features.books.mobile.speech_view.NativeSpeech', Engine),
                      patch('features.books.mobile.presentation.speech_source', source),
                      patch('features.books.mobile.presentation.wait_chapter_ready', AsyncMock(return_value=True))):
                    owner.show_read_aloud()
                    panel = owner.speech_panel
                    await panel.ready_task
                    panel.timer_choice.value = '15 min'
                    panel.change_timer()
                    await panel.play()
                    await finish_book(panel)
                    self.assertIs(owner.speech_panel, panel)
                    self.assertFalse(panel.closed)
                    self.assertEqual(owner.book_record['position'], 1, (panel.status.text, owner.book_status.text, panel.engine.calls))
                    self.assertEqual(owner.chapter_tree.current, 1)
                    self.assertEqual(len(panel.engine.calls), 2)
                    self.assertIn('first', panel.engine.calls[0][0])
                    self.assertIn('second', panel.engine.calls[1][0])
                    self.assertGreater(panel.timer.remaining, 890)
                    self.assertLessEqual(panel.timer.remaining, 900)
                    owner.close_read_aloud()
                await app.reader_manager().catalog.wait_for_refresh()
                app.readers.close(owner.session.id)
            app.loop.run_until_complete(exercise())

    def test_provider_book_transfers_panel_without_disposing_its_engine(self):
        class MemoryWebView(toga.WebView):
            def clear_private_content(self):
                self.set_content('about:blank', '')
        with reader_app() as (app, epub):
            async def exercise():
                app.show_cloud()
                private = PrivateReader('Private.epub', epub.read_bytes())
                async def source(view, chapter, offset):
                    return chapter, offset, None
                with (patch.object(app.crypt_copies, 'open', return_value=private),
                      patch('features.books.mobile.provider_reader.private_webview_supported', return_value=True),
                      patch('features.books.mobile.provider_reader.PrivateWebView', MemoryWebView),
                      patch('features.books.mobile.speech_view.NativeSpeech', Engine),
                      patch('features.books.mobile.presentation.speech_source', source),
                      patch('features.books.mobile.presentation.wait_chapter_ready', AsyncMock(return_value=True))):
                    self.assertTrue(await app.open_crypt(copies=app.crypt_copies, key='a' * 32))
                    owner = app.private_sessions.active
                    old = owner.provider_epub_view
                    owner.show_provider_read_aloud()
                    panel = old.speech_panel
                    await panel.ready_task
                    await panel.play()
                    await finish_book(panel)
                    current = owner.provider_epub_view
                    self.assertIsNot(current, old)
                    self.assertTrue(old.disposed)
                    self.assertIs(current.speech_panel, panel)
                    self.assertIs(panel.book_view, current)
                    self.assertFalse(panel.engine.closed)
                    self.assertEqual(current.chapters.current, 1)
                    self.assertEqual(len(panel.engine.calls), 2)
                    self.assertTrue(app.private_sessions.close(owner.session.id, discard=True))
                    self.assertTrue(panel.engine.closed)
            app.loop.run_until_complete(exercise())

    def test_selection_does_not_advance_and_stop_cancels_pending_speech(self):
        async def exercise():
            loop = asyncio.get_running_loop()
            source = AsyncMock(return_value=(SimpleNamespace(text='One short chapter.'), 0, 3))
            advance = AsyncMock(return_value=True)
            panel = ReadAloudPanel(loop=loop, source=source, on_range=Mock(), close=Mock(),
                                   engine=Engine(loop), next_chapter=advance)
            try:
                await panel.ready_task
                await panel.play()
                panel.session.completed(panel.session.token)
                await asyncio.sleep(0)
                advance.assert_not_called()
                source.return_value = (SimpleNamespace(text='One short chapter.'), 0, None)
                waiting, release = asyncio.Event(), asyncio.Event()
                async def delayed(panel):
                    waiting.set()
                    await release.wait()
                    return True
                panel.next_chapter = delayed
                await panel.play()
                panel.session.completed(panel.session.token)
                await waiting.wait()
                calls = len(panel.engine.calls)
                panel.session.stop()
                release.set()
                await panel.continuation_task
                self.assertEqual(len(panel.engine.calls), calls)
                self.assertEqual(panel.session.state, 'stopped')
            finally:
                panel.dispose()
        asyncio.run(exercise())
