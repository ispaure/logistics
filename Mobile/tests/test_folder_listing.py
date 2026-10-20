"""Folder reads publish only into the browser and credentials that requested them."""
import asyncio
from threading import Event, get_ident
from types import SimpleNamespace as NS
import unittest

from logisticsmobile.folder_listing import FolderListing


class FolderListingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.host = NS(active=True, context=object(), location=('Local', ''), client=object(), generation=1)
        self.listing = self.owner()

    def owner(self):
        return FolderListing(active=lambda: self.host.active, context=lambda: self.host.context,
            location=lambda: self.host.location,
            credentials=lambda: (self.host.client, self.host.generation))

    def request(self, provider, owner=None):
        owner = owner or self.listing
        return owner.capture(owner.begin(), provider, '', self.host.location)

    async def blocked_read(self, change, *, private=False, failed=False):
        entered, release = Event(), Event()
        ui_thread = get_ident()
        calls = []
        def read(folder, *, cancelled):
            calls.append((folder, get_ident()))
            entered.set()
            if not release.wait(5):
                raise RuntimeError('Test did not release folder read')
            if failed:
                raise OSError('Old listing error')
            return [{'name': 'old'}]  # Deliberately ignore cancellation like a blocking provider.
        request = self.request(NS(private=private, list=read))
        task = asyncio.create_task(self.listing.read(request))
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 5))
            change()
        finally:
            release.set()
        result = await task
        self.assertEqual(calls[0][0], '')
        self.assertNotEqual(calls[0][1], ui_thread)
        return result

    async def test_superseded_success_and_error_are_discarded(self):
        for failed in (False, True):
            with self.subTest(failed=failed):
                self.assertIsNone(await self.blocked_read(self.listing.begin, failed=failed))

    async def test_navigation_browser_and_host_changes_discard_success_and_error(self):
        for field, value in [('location', ('Local', 'new')), ('context', object()), ('active', False)]:
            for failed in (False, True):
                with self.subTest(field=field, failed=failed):
                    self.host.active = True
                    self.host.context = object()
                    self.host.location = ('Local', '')
                    self.assertIsNone(await self.blocked_read(
                        lambda: setattr(self.host, field, value), failed=failed))

    async def test_private_reads_reject_replaced_client_and_generation(self):
        for field, value in [('client', object()), ('generation', 2)]:
            for failed in (False, True):
                with self.subTest(field=field, failed=failed):
                    self.host.generation = 1
                    # A different object with the same generation must also invalidate.
                    self.assertIsNone(await self.blocked_read(
                        lambda: setattr(self.host, field, value if field == 'generation' else object()),
                        private=True, failed=failed))

    async def test_explicit_lock_invalidates_without_credential_change(self):
        for failed in (False, True):
            self.assertIsNone(await self.blocked_read(self.listing.invalidate, private=True, failed=failed))

    async def test_local_read_survives_unrelated_credential_change(self):
        self.assertEqual(await self.blocked_read(lambda: setattr(self.host, 'client', object())),
                         [{'name': 'old'}])

    async def test_current_error_is_reported_and_empty_result_is_valid(self):
        def fail(folder, *, cancelled):
            raise OSError('Current folder error')
        with self.assertRaisesRegex(OSError, 'Current folder error'):
            await self.listing.read(self.request(NS(list=fail)))
        self.assertEqual(await self.listing.read(self.request(NS(list=lambda folder, **kw: []))), [])

    async def test_browser_instances_do_not_cancel_each_other(self):
        first = self.request(NS(list=lambda folder, **kw: ['first']))
        other = self.owner()
        second = self.request(NS(list=lambda folder, **kw: ['second']), other)
        self.assertEqual(await self.listing.read(first), ['first'])
        self.assertEqual(await other.read(second), ['second'])
        self.assertFalse(first.work.cancel.is_set())

    async def test_async_cancellation_signals_worker(self):
        entered, release = Event(), Event()
        def read(folder, *, cancelled):
            entered.set()
            release.wait(5)
            return []
        request = self.request(NS(list=read))
        task = asyncio.create_task(self.listing.read(request))
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 5))
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(request.work.cancel.is_set())
            self.assertIsNone(request.work.task)
        finally:
            release.set()

    async def test_captured_selection_source_retains_filtering_boundary(self):
        calls = []
        provider = NS(private=True, list=lambda *a, **kw: self.fail('Wrong list source'))
        selection = NS(list=lambda folder, **kw: calls.append(folder) or ['filtered'])
        request = self.listing.capture(self.listing.begin(), provider, 'chosen',
                                       self.host.location, source=selection)
        self.assertEqual(await self.listing.read(request), ['filtered'])
        self.assertEqual(calls, ['chosen'])


class FolderListingAdapterTests(unittest.TestCase):
    def test_newer_main_and_workspace_loads_keep_rows_when_old_load_finishes_or_fails(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from commonUtils.runtime.local_files import LocalFiles
        from logisticsmobile.app import LogisticsMobile
        from logisticsmobile.workspace_navigation import FileDrawer

        for adapter in ('main', 'drawer'):
            for failed in (False, True):
                with self.subTest(adapter=adapter, failed=failed), TemporaryDirectory() as directory:
                    LogisticsMobile.storage_root = Path(directory)
                    app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
                    entered, release = Event(), Event()
                    class DelayedFiles(LocalFiles):
                        calls = 0
                        def list(self, folder='', *, cancelled=lambda: False):
                            self.calls += 1
                            if self.calls == 1:
                                entered.set()
                                if not release.wait(5):
                                    raise RuntimeError('Adapter fixture was not released')
                                if failed:
                                    raise OSError('Superseded adapter failure')
                            # Ignore cancellation to exercise the publication guard.
                            return super().list(folder)
                    async def exercise():
                        await app.show_files()
                        provider = DelayedFiles(app.file_provider.root)
                        (provider.root / 'kept.txt').write_text('kept')
                        if adapter == 'main':
                            owner = app
                            target, method = app, 'file_provider_for'
                            refresh = lambda: app.browse_local_during_transfer('')
                            status = app.file_status
                        else:
                            owner = FileDrawer(app.adaptive, 'home')
                            owner.available_roots = lambda: {'Local files': None}
                            target, method = app, 'storage_provider'
                            refresh = owner.refresh
                            status = owner.status
                        with patch.object(target, method, return_value=provider):
                            old = asyncio.create_task(refresh())
                            try:
                                self.assertTrue(await asyncio.to_thread(entered.wait, 5))
                                self.assertTrue(await refresh())
                                current_status = status.value
                            finally:
                                release.set()
                            self.assertFalse(await old)
                            self.assertEqual(status.value, current_status)
                            self.assertIs(owner.file_provider if adapter == 'main' else owner.provider, provider)
                            if adapter == 'main':
                                self.assertIn('kept.txt', [row['name'] for row in app.file_rows.values()])
                    try:
                        app.loop.run_until_complete(exercise())
                    finally:
                        release.set()
                        app.main_window.close()
                        app.loop.close()
                        LogisticsMobile.storage_root = None
