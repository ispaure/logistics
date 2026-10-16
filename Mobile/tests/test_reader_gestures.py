"""Library and provider gestures share session lifetime and single-flight rules."""
import asyncio
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock

from logisticsmobile.reader_chrome import ReaderChrome
from logisticsmobile.provider_ui import ProviderUI
from logisticsmobile.reader_controls import schedule_swipe


class ReaderGestureTests(unittest.IsolatedAsyncioTestCase):
    async def test_comic_adapters_reject_busy_closed_and_inactive_sessions(self):
        for provider in (False, True):
            for blocked in ('busy', 'closed', 'inactive', None):
                for rtl in (False, True):
                    with self.subTest(provider=provider, blocked=blocked, rtl=rtl):
                        reader = NS(editable=False, comic_navigation=object(), right_to_left=rtl)
                        move = AsyncMock()
                        owner = NS(crypt_reader=reader, book_reader=reader,
                            cloud_busy=blocked == 'busy', book_busy=blocked == 'busy',
                            active_host=blocked != 'inactive', session=NS(id='reader'),
                            workspace=NS(sessions={} if blocked == 'closed' else {'reader': object()}),
                            loop=asyncio.get_running_loop(), move_comic=move, move_provider_comic=move)
                        swipe = ProviderUI.swipe_crypt_page if provider else ReaderChrome.swipe_book_page
                        swipe(owner, 1)
                        # A second native gesture before the queued operation runs
                        # must not load another spread or skip the following page.
                        swipe(owner, 1)
                        task = getattr(owner, '_comic_swipe_task', None)
                        if blocked is not None:
                            self.assertIsNone(task)
                            move.assert_not_called()
                        else:
                            await task
                            move.assert_awaited_once_with(-1 if rtl else 1)
                            swipe(owner, -1)
                            await owner._comic_swipe_task
                            self.assertEqual(move.await_args.args, (1 if rtl else -1,))

    async def test_absolute_page_gestures_keep_bounds_and_manga_direction(self):
        for rtl in (False, True):
            for position in (0, 1, 2):
                for direction in (-1, 1):
                    with self.subTest(rtl=rtl, position=position, direction=direction):
                        move = AsyncMock()
                        owner = NS(active_host=True, session=NS(id='reader'),
                                   workspace=NS(sessions={'reader': object()}), loop=asyncio.get_running_loop())
                        schedule_swipe(owner, direction, position=position, count=3,
                                       right_to_left=rtl, busy=False, move=move)
                        target = position + (-direction if rtl else direction)
                        task = getattr(owner, '_comic_swipe_task', None)
                        if 0 <= target < 3:
                            await task
                            move.assert_awaited_once_with(target)
                        else:
                            self.assertIsNone(task)
                            move.assert_not_called()
