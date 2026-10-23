"""Shared scrubbing semantics for comic pages, PDF pages and EPUB chapters."""
import asyncio
import unittest
from unittest.mock import AsyncMock

import toga
from mobile.reader_controls import PageFooter, page_buttons


class ReaderProgressTests(unittest.TestCase):
    def footer(self, **kwargs):
        move = AsyncMock()
        return PageFooter(*page_buttons(None, None), move, **kwargs), move

    def test_page_and_chapter_tracks_commit_only_on_release(self):
        for unit in ('page', 'chapter'):
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
        self.assertIs(footer.widget.children[0], footer.following)
        self.assertEqual(footer.spacer.text, '3–4/82 · 1/2')
        footer.slider.value = 0
        asyncio.run(footer.release(footer.slider))
        move.assert_awaited_once_with(81)

    def test_chapter_badge_keeps_detailed_accessibility_label(self):
        footer, _ = self.footer(unit='chapter')
        footer.sync(comic=False, count=12, index=2)
        footer.chapter_progress(2, 12, 25, 100)
        self.assertEqual(footer.spacer.text, '3/12 · 25%')
        self.assertEqual(footer.spacer.accessible_name, 'Chapter 3 of 12, 25% through chapter')
