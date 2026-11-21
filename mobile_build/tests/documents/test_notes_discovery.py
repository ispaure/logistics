"""Cancellation and credential changes during Notes discovery and row activation."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
import gc
from threading import Event
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, Mock, patch

import toga
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.settings import WAIT_TIMEOUT
from commonUtils.testing.stages import TestStage
from mobile.notes_discovery import populate
from mobile_build.tests.support.app import create_app

TEST_STAGE = TestStage.REGRESSION


class _LocalLease(LocalFiles):
    closed = False

    def close(self):
        self.closed = True


class NotesDiscoveryTests(TestCase):
    def setUp(self):
        self.app = create_app(self)
        self.container = toga.Box()
        self.client = SimpleNamespace(generation=1)
        self.enterContext(patch.object(self.app, 'cloud_client', self.client, create=True))
        self.enterContext(patch.object(self.app, 'home_unlock_candidates', return_value=[]))
        self.enterContext(patch.object(self.app, 'existing_crypt_locations', return_value={}))

    def test_generation_change_suppresses_a_late_scan_and_releases_its_provider(self):
        app = self.app
        root = app.private_root / 'Fixture'
        (root / '.obsidian').mkdir(parents=True)
        provider = _LocalLease(root)
        started, release = Event(), Event()
        list_folder = provider.list

        def delayed_list(*args, **kwargs):
            rows = list_folder(*args, **kwargs)
            started.set()
            release.wait(WAIT_TIMEOUT)
            return rows

        async def exercise():
            populate(app, self.container, refresh=False)
            rows, status = self.container.children[1:3]
            pending_status = status.text
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, WAIT_TIMEOUT))
                self.client.generation += 1
            finally:
                release.set()
                await asyncio.wait_for(app._notes_discovery_task, WAIT_TIMEOUT)
            self.assertEqual(list(rows.children), [])
            self.assertEqual(status.text, pending_status)
            self.assertTrue(provider.closed)

        with (patch.object(app, 'ordinary_file_roots', return_value={'Fixture': provider}),
              patch.object(app, 'linked_crypt_locations', return_value={}),
              patch.object(provider, 'list', side_effect=delayed_list)):
            app.loop.run_until_complete(exercise())

    def test_replacing_the_client_during_row_activation_releases_the_reopened_provider(self):
        app = self.app
        root = app.private_root / 'Fixture'
        (root / 'Vault/.obsidian').mkdir(parents=True)
        location = SimpleNamespace(remote='Fixture')
        linked = SimpleNamespace(location=location, close=Mock())
        scanned, reopened = _LocalLease(root), _LocalLease(root)
        service = SimpleNamespace(localcrypt=SimpleNamespace(open=Mock(return_value=scanned)))
        started, release = Event(), Event()

        def reopen(location):
            started.set()
            release.wait(WAIT_TIMEOUT)
            return reopened

        async def exercise(open_vault):
            populate(app, self.container, refresh=False)
            await asyncio.wait_for(app._notes_discovery_task, WAIT_TIMEOUT)
            button, = self.container.children[1].children
            self.assertEqual(button.accessible_name, 'Vault · Fixture - Encrypted Copy')
            linked.close.assert_called_once()
            self.assertTrue(scanned.closed)

            service.localcrypt.open.side_effect = reopen
            opening = button.on_press()
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, WAIT_TIMEOUT))
                app.cloud_client = SimpleNamespace(generation=self.client.generation)
            finally:
                release.set()
                await asyncio.wait_for(opening, WAIT_TIMEOUT)
            open_vault.assert_not_called()
            self.assertTrue(reopened.closed)

        with (patch.object(app, 'ordinary_file_roots', return_value={}),
              patch.object(app, 'linked_crypt_locations',
                           return_value={'Fixture · Fixture - Encrypted Copy': linked}),
              patch('features.rclone.mobile.service.native_service', return_value=service),
              patch('mobile.obsidian.open_vault', new_callable=AsyncMock) as open_vault):
            app.loop.run_until_complete(exercise(open_vault))

    def _cancel_row_during_acquisition(self, reopen):
        app = self.app
        root = app.private_root / 'Fixture'
        (root / 'Vault/.obsidian').mkdir(parents=True)
        started, release, finished = Event(), Event(), Event()
        loop_errors = []

        def blocked_reopen(label, roots):
            started.set()
            try:
                if not release.wait(WAIT_TIMEOUT):
                    raise TimeoutError('Test did not release the provider factory')
                return reopen()
            finally:
                finished.set()

        async def exercise(storage_provider, open_vault):
            populate(app, self.container, refresh=False)
            await asyncio.wait_for(app._notes_discovery_task, WAIT_TIMEOUT)
            rows, status = self.container.children[1:3]
            button, = rows.children
            storage_provider.side_effect = blocked_reopen
            opening = button.on_press()
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, WAIT_TIMEOUT))
                opening.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(asyncio.shield(opening), WAIT_TIMEOUT)
                self.assertFalse(finished.is_set())
            finally:
                release.set()
                await asyncio.wait_for(app.loop.shutdown_default_executor(), WAIT_TIMEOUT)
            # Let the joined worker's completion callback run and surface any
            # unobserved exception before restoring the loop's error handler.
            await asyncio.sleep(0)
            gc.collect()
            open_vault.assert_not_called()
            self.assertEqual(status.text, '')
            self.assertEqual(loop_errors, [])

        previous_handler = app.loop.get_exception_handler()
        app.loop.set_exception_handler(lambda loop, context: loop_errors.append(context))
        try:
            with (patch.object(app, 'ordinary_file_roots', return_value={'Fixture': None}),
                  patch.object(app, 'linked_crypt_locations', return_value={}),
                  patch.object(app, 'storage_provider', return_value=LocalFiles(root)) as storage_provider,
                  patch('mobile.obsidian.open_vault', new_callable=AsyncMock) as open_vault):
                app.loop.run_until_complete(exercise(storage_provider, open_vault))
        finally:
            app.loop.set_exception_handler(previous_handler)

    def test_cancelled_row_closes_a_provider_returned_after_cancellation(self):
        provider = SimpleNamespace(close=Mock())
        self._cancel_row_during_acquisition(lambda: provider)
        provider.close.assert_called_once_with()

    def test_cancelled_row_consumes_a_late_provider_error(self):
        def reopen():
            raise OSError('Test provider unavailable')

        self._cancel_row_during_acquisition(reopen)
