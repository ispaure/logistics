"""Shared scrubbing semantics for comic pages, PDF pages and EPUB chapters."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

import toga
from mobile.reader_controls import PageFooter, page_buttons


class ReaderProgressTests(unittest.TestCase):
    def footer(self, **kwargs):
        move = AsyncMock()
        return PageFooter(*page_buttons(None, None), move, **kwargs), move

    def test_progress_caption_is_below_full_width_transport_without_a_badge_reservation(self):
        footer, _ = self.footer(unit='chapter')
        footer.chapter_progress(2, 12, 25, 100)
        self.assertEqual(list(footer.widget.children), [footer.row, footer.badge])
        self.assertEqual(list(footer.row.children), [footer.previous, footer.slider, footer.following])
        self.assertEqual(footer.spacer.style.text_align, 'center')
        self.assertEqual(footer.spacer.style.width, 1)
        self.assertNotEqual(footer.badge.style.width, 184)
        self.assertNotEqual(footer.badge.style.height, 44)

    def test_caption_width_releases_a_previous_landscape_allocation(self):
        footer, _ = self.footer(unit='chapter')
        footer.refresh_edges(750)
        self.assertEqual(footer.badge.style.width, 742)
        self.assertEqual(footer.spacer.style.width, 742)
        footer.refresh_edges(402)
        self.assertEqual(footer.badge.style.width, 394)
        self.assertEqual(footer.spacer.style.width, 394)
        footer.refresh_edges(402)
        self.assertEqual(footer.badge.style.width, 394)

    def test_page_and_chapter_tracks_commit_only_on_release(self):
        for unit in ('page',):
            with self.subTest(unit=unit):
                footer, move = self.footer(unit=unit)
                footer.sync(comic=False, count=8, index=2)
                self.assertTrue(footer.slider.enabled)
                footer.slider.value = 5
                move.assert_not_called()
                asyncio.run(footer.release(footer.slider))
                move.assert_awaited_once_with(5)
                self.assertEqual(footer.slider.value, 2)  # Await successful publication.
                self.assertEqual(footer.slider.accessible_name, unit.title() + ' position')

    def test_single_page_track_is_disabled_and_failed_scrub_returns_to_current_page(self):
        footer, move = self.footer()
        footer.sync(comic=False, count=1, index=0)
        asyncio.run(footer.release(footer.slider))
        move.assert_not_called()
        footer.sync(comic=False, count=4, index=1)
        footer.slider.value = 3
        move.side_effect = OSError('Page unavailable')
        with self.assertRaises(OSError):
            asyncio.run(footer.release(footer.slider))
        self.assertEqual(footer.slider.value, 1)

    def test_manga_preserves_direction_and_compact_spread_description(self):
        status = toga.Label('Page 3–4/82 · 1/2 · Right-to-left manga')
        footer, move = self.footer(status=status)
        footer.sync(comic=True, count=82, index=2, right_to_left=True)
        self.assertIs(footer.row.children[0], footer.following)
        self.assertEqual(footer.spacer.text, '3–4/82 · 1/2')
        footer.slider.value = 0
        asyncio.run(footer.release(footer.slider))
        move.assert_awaited_once_with(81)

    def test_manga_fill_direction_survives_theme_refresh_and_mode_changes(self):
        from mobile.reader_progress import style_slider
        footer, _ = self.footer()
        with patch('mobile.reader_progress.native_style_slider') as paint:
            for rtl in (True, False, True):
                footer.sync(comic=True, count=5, index=1, right_to_left=rtl)
                style_slider(footer.slider)
                self.assertEqual(footer.slider.value, 3 if rtl else 1)
                self.assertEqual(paint.call_args.kwargs['reverse_fill'], rtl)
                self.assertTrue(paint.call_args.kwargs['force_ltr'])

    def test_both_axes_share_disabled_failed_and_successful_release_semantics(self):
        for vertical in (False, True):
            with self.subTest(vertical=vertical):
                footer, move = self.footer(vertical=vertical)
                footer.sync(comic=False, count=1, index=0)
                asyncio.run(footer.release(footer.slider))
                move.assert_not_called()
                if vertical:
                    footer.slider.drag_track(footer.slider, 22, 80)
                    asyncio.run(footer.slider.release_track(footer.slider, 22, 80))
                    self.assertEqual(footer.slider.value, 0)
                    move.assert_not_called()
                footer.sync(comic=False, count=8, index=2)
                footer.slider.value = 4.6
                move.side_effect = OSError('Unavailable')
                with self.assertRaises(OSError):
                    asyncio.run(footer.release(footer.slider))
                self.assertEqual(footer.slider.value, 2)
                move.side_effect = None
                footer.slider.value = 4.6
                asyncio.run(footer.release(footer.slider))
                move.assert_awaited_with(5)
                self.assertEqual(footer.slider.value, 2)

    def test_chapter_badge_keeps_detailed_accessibility_label(self):
        footer, _ = self.footer(unit='chapter')
        footer.sync(comic=False, count=12, index=2)
        footer.chapter_progress(2, 12, 25, 100)
        self.assertEqual(footer.spacer.text, 'Counting pages…\nChapter 3 of 12')
        self.assertEqual(footer.spacer.accessible_name, 'Counting pages… · Chapter 3 of 12')
        self.assertFalse(footer.slider.enabled)

    def test_book_page_scrub_uses_rendered_counts_and_single_chapter_is_enabled(self):
        from features.books.mobile.pagination import MobilePagination
        footer, _ = self.footer(unit='chapter')
        seek = AsyncMock()
        book = Mock(spine=['short', 'long'])
        footer.set_book(book, seek)
        pagination = MobilePagination(book, footer.show_epub_pages)
        pagination.chapter, pagination.page = 1, 3
        pagination.pages.record(0, 2)
        pagination.pages.record(1, 8)
        pagination.text_lengths = [150, 250]
        pagination.text_starts = (0, 150, 400)
        pagination.seek_page = AsyncMock()
        footer.epub_pagination = pagination
        footer.sync(comic=False, count=2, index=1)
        footer.chapter_progress(1, 2, 50, 100)
        self.assertEqual(footer.slider.value, .6)
        self.assertEqual(footer.spacer.text, '50% · Page 6 of 10\nChapter 2 of 2')
        footer.slider.value = .1
        asyncio.run(footer.release(footer.slider))
        seek.assert_awaited_once_with(0, 0)
        pagination.seek_page.assert_awaited_once_with(0, 1)
        single_chapter = Mock(spine=['one'])
        footer.set_book(single_chapter, seek)
        pagination = MobilePagination(single_chapter, footer.show_epub_pages)
        pagination.page = 3
        pagination.pages.record(0, 8)
        footer.epub_pagination = pagination
        footer.sync(comic=False, count=1, index=0)
        footer.chapter_progress(0, 1, 50, 100)
        self.assertTrue(footer.slider.enabled)
        self.assertEqual(footer.slider.value, .5)

    def test_pdf_vertical_track_increases_downward_and_commits_only_on_release(self):
        footer, move = self.footer(vertical=True)
        footer.sync(comic=False, count=5, index=0)
        slider = footer.slider
        slider.resize_track(slider, 44, 124)
        slider.drag_track(slider, 22, 87)
        self.assertEqual(slider.value, 3)
        move.assert_not_called()
        asyncio.run(slider.release_track(slider, 22, 87))
        move.assert_awaited_once_with(3)
        self.assertEqual(slider.value, 0)


class ProviderProgressLifetimeTests(unittest.IsolatedAsyncioTestCase):
    def progress(self):
        from types import SimpleNamespace as NS
        from unittest.mock import Mock
        from mobile.provider_progress import ProgressWrites, ProviderProgress
        from services.documents.progress import ProgressStatus

        owner = NS(active_host=True, crypt_reader=NS(labels=['page']),
                   crypt_page=NS(value='page'), loop=asyncio.get_running_loop())
        progress = ProviderProgress.__new__(ProviderProgress)
        state = NS(flush=Mock(return_value=ProgressStatus.SAVED), retire=Mock(),
                   observe=lambda value: value, load_status=ProgressStatus.ABSENT,
                   write_status=ProgressStatus.SAVED)
        ProgressWrites.__init__(progress, owner, state)
        progress.pending = {'page': 0}
        progress.surface = progress.surface_task = None
        progress.surface_ready = False
        progress.last_location = {'page': 0}
        progress.worker_finished = lambda: None
        progress.available = lambda: (not progress.closed and owner.active_host
                                      and not getattr(getattr(owner, '_provider_document', None), 'terminal', False))
        return progress

    async def test_cancelled_progress_write_retains_borrow_until_real_worker_finishes(self):
        from threading import Event
        progress = self.progress()
        entered, release, finished = asyncio.Event(), Event(), Event()
        loop = asyncio.get_running_loop()
        def save(value):
            loop.call_soon_threadsafe(entered.set)
            try:
                if not release.wait(5):
                    raise RuntimeError('Fixture not released')
            finally:
                finished.set()
        progress.state.flush.side_effect = save
        progress.task = asyncio.create_task(progress.write())
        try:
            await asyncio.wait_for(entered.wait(), 2)
            progress.task.cancel()
            await asyncio.sleep(0)
            progress.task.cancel()
            await asyncio.sleep(0)
            self.assertFalse(progress.task.done())
            self.assertIsNotNone(progress.worker)
            with self.assertRaises(OSError):
                progress.close()
            with self.assertRaises(OSError):
                progress.retire()
            self.assertFalse(progress.closed)
        finally:
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await progress.task
            self.assertTrue(await asyncio.to_thread(finished.wait, 2))
        progress.retire()
        self.assertTrue(progress.closed)
        progress.state.flush.assert_called_once_with({'page': 0})

    async def test_preparation_flushes_without_observing_the_closing_window_again(self):
        progress = self.progress()
        await progress.prepare_replacement()
        progress.state.flush.assert_called_once_with({'page': 0})
        self.assertEqual(progress.generation, 0)
        progress.retire()
        progress.retire()
        progress.observe({'page': 1})
        progress.state.flush.assert_called_once()
        self.assertTrue(progress.closed)

    async def test_write_failure_retains_latest_observation_for_retry(self):
        from services.documents.progress import ProgressStatus
        progress = self.progress()
        progress.state.flush.side_effect = [ProgressStatus.WRITE_FAILED, ProgressStatus.SAVED]
        self.assertIs(await progress.flush(), ProgressStatus.WRITE_FAILED)
        self.assertEqual(progress.pending, {'page': 0})
        progress.observe({'page': 1})
        await progress.flush()
        self.assertEqual(progress.state.flush.call_args.args[0], {'page': 1})
        self.assertIsNone(progress.pending)
        progress.retire()

    async def test_final_progress_capture_invalidates_receipt_when_changed_during_save(self):
        from threading import Event
        progress = self.progress()
        entered, release = asyncio.Event(), Event()
        loop = asyncio.get_running_loop()
        writes = []
        def save(value):
            writes.append(value)
            loop.call_soon_threadsafe(entered.set)
            if not release.wait(5):
                raise RuntimeError('Fixture not released')
        progress.state.flush.side_effect = save
        task = asyncio.create_task(progress.prepare_replacement())
        try:
            await asyncio.wait_for(entered.wait(), 2)
            progress.observe({'page': 1})
        finally:
            release.set()
            with self.assertRaises(OSError):
                await task
        self.assertFalse(progress.closed)
        self.assertEqual(len(writes), 2)
        self.assertEqual(writes[-1], {'page': 1})

    async def test_document_disposal_and_reader_assignment_reject_progress_borrow(self):
        from types import SimpleNamespace as NS
        from threading import Event
        from unittest.mock import Mock
        from mobile.provider_document import ProviderDocumentSession
        progress = self.progress()
        reader = NS(labels=['page'], kind='.pdf', source=NS(close=Mock()), pdf=NS(close=Mock()))
        owner = progress.owner
        owner._provider_progress = progress
        document = ProviderDocumentSession(owner)
        document.reader = reader
        owner.crypt_reader = reader
        entered, release = asyncio.Event(), Event()
        loop = asyncio.get_running_loop()
        def save(state):
            loop.call_soon_threadsafe(entered.set)
            if not release.wait(5):
                raise RuntimeError('Fixture not released')
        progress.state.flush.side_effect = save
        progress.task = asyncio.create_task(progress.write(delay=False))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            with self.assertRaises(OSError):
                document.dispose()
            with self.assertRaises(OSError):
                document.reader = NS(source=NS(close=Mock()))
            self.assertFalse(document.can_start())
            reader.pdf.close.assert_not_called()
            reader.source.close.assert_not_called()
            progress.task.cancel()
            await asyncio.sleep(0)
            progress.task.cancel()
            await asyncio.sleep(0)
            self.assertFalse(progress.task.done())
        finally:
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await progress.task
        self.assertTrue(document.can_start())
        document.terminal = True
        with patch('mobile.external_display.sync'), patch('mobile.ios_content_background.clear'):
            document.dispose()
        reader.pdf.close.assert_called_once_with()
        reader.source.close.assert_called_once_with()
        self.assertEqual(progress.state.flush.call_count, 1)

    async def test_terminal_admission_fences_reentrant_footer_capture_before_source_close(self):
        from types import SimpleNamespace as NS
        from unittest.mock import Mock
        from mobile.provider_document import ProviderDocumentSession
        from mobile.private_sessions import PrivateSessions
        progress = self.progress()
        progress.pending = None
        owner = progress.owner
        owner.app = owner
        owner.session = NS(id='doc')
        reader = owner.crypt_reader = NS(labels=['page'], kind='.pdf', source=NS(close=Mock()), pdf=NS(close=Mock()))
        owner._provider_progress = progress
        document = owner._provider_document = ProviderDocumentSession(owner)
        document.reader = reader
        owner.provider_document = lambda: document
        owner.crypt_view = NS(page_footer=NS(dispose=Mock(side_effect=progress.capture)))
        manager = PrivateSessions.__new__(PrivateSessions)
        manager.controllers, manager.app, manager.terminal = {'doc': owner}, owner, False
        owner.manager, owner.private_sessions = manager, manager
        manager._admit_retirement()
        with patch('mobile.external_display.sync'), patch('mobile.ios_content_background.clear'):
            manager.retire()
            manager.retire()
        progress.capture()
        await progress.write(delay=False)
        self.assertIsNone(progress.task)
        self.assertIsNone(progress.pending)
        progress.state.flush.assert_not_called()
        reader.source.close.assert_called_once_with()
        reader.pdf.close.assert_called_once_with()
        owner.crypt_view.page_footer.dispose.assert_called_once_with()
