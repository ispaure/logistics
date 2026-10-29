"""Shared scrubbing semantics for comic pages, PDF pages and EPUB chapters."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

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
        from types import SimpleNamespace
        from features.books.locations import LayoutPages
        footer, _ = self.footer(unit='chapter')
        seek = AsyncMock()
        book = SimpleNamespace(spine=['short', 'long'], resource_sizes={'short': 100, 'long': 300})
        footer.set_book(book, seek)
        pages = LayoutPages(2)
        pages.reset('portrait'); pages.record(0, 2); pages.record(1, 8)
        pagination = SimpleNamespace(pages=pages, seek_page=AsyncMock(),
            publish=lambda: footer.show_epub_pages(pages.position(1, 3)))
        footer.epub_pagination = pagination
        footer.sync(comic=False, count=2, index=1)
        footer.chapter_progress(1, 2, 50, 100)
        self.assertEqual(footer.slider.value, .6)
        self.assertEqual(footer.spacer.text, '60% · Page 6 of 10\nChapter 2 of 2')
        footer.slider.value = .1
        asyncio.run(footer.release(footer.slider))
        seek.assert_awaited_once_with(0, 0)
        pagination.seek_page.assert_awaited_once_with(0, 1)
        footer.epub_pagination = None
        footer.set_book(SimpleNamespace(spine=['one'], resource_sizes={}), seek)
        pages = LayoutPages(1); pages.reset('portrait'); pages.record(0, 8)
        footer.epub_pagination = SimpleNamespace(pages=pages,
            publish=lambda: footer.show_epub_pages(pages.position(0, 3)))
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
