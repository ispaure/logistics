"""Neighbor hints follow current lookup/access state without changing folders."""

import asyncio
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock, patch

from commonUtils.testing.stages import TestStage
from features.comics.mobile.navigation import folder_comics
from features.comics.mobile.provider_controller import ProviderComicController
from features.comics.mobile.reader_controller import ComicController

TEST_STAGE = TestStage.REGRESSION


class Header:
    available = (False, False)

    def sync(self, previous, following):
        self.available = previous, following


def reader_fixture(provider):
    prefix = 'Comics/' if provider else ''
    reader = NS(key=prefix + '02.cbz', kind='.cbz', book=None, editable=False)
    owner = NS(active_host=True, navigation_generation=0, access=True, session=NS(id='reader'),
               book_reader=reader, crypt_reader=reader, book_busy=False, cloud_busy=False,
               book_record=dict(id='record', kind='comic'), book_status=NS(text=''), crypt_title=NS(text=''),
               comic_header=Header(), crypt_immersive=True, presentation_destination='documents',
               feedback_visible=True, rows=[])
    owner.workspace = NS(token=lambda key: key, accepts=lambda token: owner.access)
    owner.manager = NS(active=owner, available=lambda key: owner.access,
                       open=AsyncMock(return_value=False), close=Mock())
    owner.format_services = NS(private_label=lambda text: text,
                              clear_comic_boundary=lambda: setattr(owner, 'feedback_visible', False))
    owner.open_comic_neighbor = AsyncMock(return_value=False)
    owner._crypt_reader_store = NS(provider=NS(list=lambda folder: owner.rows))
    owner.comic_file_entries = lambda: (Path('/synthetic/02.cbz'), folder_comics(owner.rows, reader.key))
    controller = ProviderComicController(owner) if provider else ComicController(owner)
    refresh = controller.refresh_provider_comic_neighbors if provider else controller.refresh_comic_neighbors
    adjacent = controller.adjacent_provider_comic if provider else controller.adjacent_book_comic

    def neighbors(previous=True, following=True):
        names = ['02.cbz', 'notes.txt', 'Other/00.cbz']
        names += ['01.cbz'] if previous else []
        names += ['03.cbz'] if following else []
        owner.rows = [dict(path=prefix + name, name=name.rsplit('/', 1)[-1], directory=False)
                      for name in names]

    neighbors()
    return owner, refresh, adjacent, neighbors


class ComicNeighborGuidanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_corresponding_neighbor_flags_ignore_other_folders_and_formats(self):
        for provider in (False, True):
            for previous, following in ((False, False), (True, False), (False, True), (True, True)):
                with self.subTest(provider=provider, previous=previous, following=following):
                    owner, refresh, _, neighbors = reader_fixture(provider)
                    neighbors(previous, following)
                    await refresh()
                    self.assertEqual(owner.comic_header.available, (previous, following))

    async def test_pending_and_failed_lookup_remove_old_instruction(self):
        for provider in (False, True):
            with self.subTest(provider=provider):
                owner, refresh, _, _ = reader_fixture(provider)
                await refresh()
                self.assertEqual(owner.comic_header.available, (True, True))
                owner.feedback_visible = True
                entered, release = asyncio.Event(), asyncio.Event()

                async def fail(function, *args):
                    entered.set()
                    await release.wait()
                    raise OSError('Synthetic provider is unavailable')

                with patch('asyncio.to_thread', side_effect=fail):
                    task = asyncio.create_task(refresh())
                    await asyncio.wait_for(entered.wait(), 1)
                    self.assertEqual(owner.comic_header.available, (False, False))
                    self.assertFalse(owner.feedback_visible)
                    release.set()
                    await task
                self.assertEqual(owner.comic_header.available, (False, False))

    async def test_older_lookup_cannot_restore_hint_after_newer_empty_listing(self):
        for provider in (False, True):
            with self.subTest(provider=provider):
                owner, refresh, _, neighbors = reader_fixture(provider)
                entered, release = asyncio.Event(), asyncio.Event()
                first = True

                async def list_rows(function, *args):
                    nonlocal first
                    result = function(*args)
                    if first:
                        first = False
                        entered.set()
                        await release.wait()
                    return result

                with patch('asyncio.to_thread', side_effect=list_rows):
                    old = asyncio.create_task(refresh())
                    await asyncio.wait_for(entered.wait(), 1)
                    neighbors(False, False)
                    await refresh()
                    release.set()
                    await old
                self.assertEqual(owner.comic_header.available, (False, False))

    async def test_disappeared_volume_reports_error_and_preserves_current_reader(self):
        for provider in (False, True):
            for direction in (-1, 1):
                with self.subTest(provider=provider, direction=direction):
                    owner, refresh, adjacent, neighbors = reader_fixture(provider)
                    await refresh()
                    reader = owner.crypt_reader if provider else owner.book_reader
                    neighbors(direction > 0, direction < 0)
                    message = await adjacent(direction)
                    self.assertEqual(message, ('Previous' if direction < 0 else 'Next') +
                                     ' volume is no longer available.')
                    self.assertIs(owner.crypt_reader if provider else owner.book_reader, reader)
                    self.assertFalse(owner.comic_header.available[0 if direction < 0 else 1])
                    owner.manager.open.assert_not_awaited()
                    owner.open_comic_neighbor.assert_not_awaited()
                    owner.manager.close.assert_not_called()

    async def test_navigation_or_reader_close_during_lookup_cannot_open_neighbor(self):
        for provider in (False, True):
            for change in ('route', 'reader', 'access'):
                with self.subTest(provider=provider, change=change):
                    owner, _, adjacent, _ = reader_fixture(provider)
                    entered, release = asyncio.Event(), asyncio.Event()

                    async def list_rows(function, *args):
                        result = function(*args)
                        entered.set()
                        await release.wait()
                        return result

                    with patch('asyncio.to_thread', side_effect=list_rows):
                        task = asyncio.create_task(adjacent(1))
                        await asyncio.wait_for(entered.wait(), 1)
                        if change == 'route':
                            owner.navigation_generation += 1
                        elif change == 'reader':
                            owner.book_reader = owner.crypt_reader = None
                        else:
                            owner.access = False
                        release.set()
                        self.assertIsNone(await task)
                    owner.manager.open.assert_not_awaited()
                    owner.open_comic_neighbor.assert_not_awaited()
                    owner.manager.close.assert_not_called()

    async def test_provider_access_denial_and_unsupported_reader_remove_hints(self):
        owner, refresh, adjacent, _ = reader_fixture(True)

        def capture(key):
            def check():
                if key.endswith('03.cbz'):
                    raise PermissionError('Synthetic neighboring volume is locked')
            return check

        owner._crypt_reader_store.capture_access = capture
        await refresh()
        self.assertEqual(owner.comic_header.available, (True, False))
        self.assertIn('no longer available', await adjacent(1))
        owner.manager.open.assert_not_awaited()
        owner.crypt_reader.kind = '.pdf'
        await refresh()
        self.assertEqual(owner.comic_header.available, (False, False))

    async def test_failed_open_preserves_reader_and_stops_advertising_that_target(self):
        for provider in (False, True):
            with self.subTest(provider=provider):
                owner, _, adjacent, _ = reader_fixture(provider)
                self.assertIn('current comic is still open', await adjacent(1))
                self.assertEqual(owner.comic_header.available, (True, False))
                owner.manager.close.assert_not_called()

    async def test_swipe_and_toolbar_cannot_open_two_neighbors_concurrently(self):
        for provider in (False, True):
            with self.subTest(provider=provider):
                owner, _, adjacent, _ = reader_fixture(provider)
                entered, release = asyncio.Event(), asyncio.Event()

                async def open_neighbor(*args, **kwargs):
                    entered.set()
                    await release.wait()
                    return False

                opening = owner.manager.open if provider else owner.open_comic_neighbor
                opening.side_effect = open_neighbor
                first = asyncio.create_task(adjacent(1))
                try:
                    await asyncio.wait_for(entered.wait(), 1)
                    # The lookup has finished and restored the available flags,
                    # but the first target has not finished opening yet.
                    self.assertEqual(owner.comic_header.available, (True, True))
                    self.assertIsNone(await adjacent(-1))
                    self.assertEqual(opening.await_count, 1)
                finally:
                    release.set()
                    await first
                self.assertIs(owner.manager.active, owner)
                owner.manager.close.assert_not_called()
                # A failed attempt releases the guard so another deliberate
                # action can retry through the normal lookup/open contract.
                await adjacent(-1)
                self.assertEqual(opening.await_count, 2)
