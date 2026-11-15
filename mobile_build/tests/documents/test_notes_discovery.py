"""Credential changes during Notes discovery and row activation."""
import asyncio
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
