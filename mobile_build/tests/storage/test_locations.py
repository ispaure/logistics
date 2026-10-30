
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from mobile.locations import Locations
from mobile.locations_controller import LocationsController
from mobile.composition.locations import locations_host
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import asyncio


class LocationTests(unittest.TestCase):
    def test_safe_identity_dedup_and_restart_without_private_names(self):
        with TemporaryDirectory() as folder:
            store = Locations(Path(folder))
            local = store.pin('local', 'notes')
            self.assertEqual(store.pin('local', 'notes'), local)
            store.pin('remote', 'public/books', 'a' * 64)
            restored = Locations(Path(folder))
            self.assertEqual(restored.items, store.items)
            for kind, path in (('crypt', 'decrypted-name'), ('local', '../outside'), ('local', '/outside')):
                with self.assertRaises(ValueError):
                    store.pin(kind, path)
            self.assertNotIn('decrypted-name', store.path.read_text())
            restored.remove(local['id'])
            self.assertEqual(len(Locations(Path(folder)).items), 1)

    def test_conflict_malformed_and_links_preserved(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            one, two = Locations(root), Locations(root)
            one.pin('local', '')
            with self.assertRaises(OSError):
                two.pin('local', 'stale')
            data = b'{invalid'
            one.path.write_bytes(data)
            bad = Locations(root)
            self.assertTrue(bad.error)
            with self.assertRaises(ValueError):
                bad.pin('local', 'new')
            self.assertEqual(one.path.read_bytes(), data)
            one.path.unlink()
            target = root / 'outside'
            target.write_bytes(data)
            one.path.symlink_to(target)
            bad = Locations(root)
            with self.assertRaises(ValueError):
                bad.pin('local', '')
            self.assertEqual(target.read_bytes(), data)

    def test_controller_uses_only_injected_capabilities_and_keeps_state_off_host(self):
        from mobile.locations_controller import LocationHost
        with TemporaryDirectory() as folder:
            local_status, remote_status = Mock(), Mock()
            root = Path(folder)
            host = LocationHost(lambda: root, lambda: 'notes', AsyncMock(return_value=None),
                                local_status, remote_status, AsyncMock(), AsyncMock(), Mock())
            controller = LocationsController(host)
            controller.pin_local_folder()
            self.assertEqual(controller.pinned_locations().items[0]['path'], 'notes')
            local_status.assert_called_once_with('Folder pinned in Workspaces.')
            self.assertFalse(hasattr(host, 'locations'))
            self.assertFalse(hasattr(controller, 'app'))

    def test_real_local_pin_navigation_stops_when_checkpoint_is_vetoed(self):
        from mobile_build.tests.support.app import mobile_app
        from services.documents.locations import collection_path
        with mobile_app() as app:
            (collection_path(app.private_root) / 'Notes').mkdir(parents=True)
            app.loop.run_until_complete(app.show_files())
            original = app.file_path
            with patch.object(app, 'checkpoint', return_value=False):
                app.loop.run_until_complete(app.locations_controller().pinned_opener(
                    dict(kind='local', path='Notes'))())
            self.assertEqual(app.file_path, original)


class PinnedNavigationTests(unittest.IsolatedAsyncioTestCase):
    def host(self):
        client = SimpleNamespace(generation=1, connection_identity=Mock(return_value='a' * 64))
        host = SimpleNamespace(active_host=True, navigation_generation=1, cloud_client=client,
            cloud_remote=SimpleNamespace(items=['Public', 'Encrypted'], value='Original'),
            cloud_crypt_remotes={'Encrypted'}, cloud_restore_task=None,
            show_cloud=Mock(), show_locations=Mock(), browser_cloud_location=AsyncMock())
        host.cloud_controller = lambda: host
        host.show_local_location = AsyncMock()
        host.browser_file_location = AsyncMock()
        return host

    async def test_current_connection_opens_matching_ordinary_folder(self):
        host = self.host()
        controller = LocationsController(locations_host(host))
        await controller.pinned_opener(dict(kind='remote', connection='a' * 64, path='books'))()
        host.cloud_client.connection_identity.assert_called_once_with('Public')
        host.browser_cloud_location.assert_awaited_once_with(('Public', 'books'))
        self.assertEqual(host.cloud_remote.value, 'Public')
        host.show_locations.assert_not_called()

    async def test_replaced_or_retired_connection_cannot_navigate_after_lookup(self):
        for change in ('client', 'generation', 'selector', 'navigation', 'inactive'):
            with self.subTest(change=change):
                host = self.host()
                selector = host.cloud_remote
                controller = LocationsController(locations_host(host))
                started, release = asyncio.Event(), asyncio.Event()
                async def lookup(*args):
                    started.set()
                    await release.wait()
                    return 'a' * 64
                with patch('mobile.composition.locations.asyncio.to_thread', side_effect=lookup):
                    task = asyncio.create_task(controller.pinned_opener(
                        dict(kind='remote', connection='a' * 64, path='books'))())
                    try:
                        await asyncio.wait_for(started.wait(), 1)
                        if change == 'client':
                            host.cloud_client = SimpleNamespace(generation=1)
                        elif change == 'generation':
                            host.cloud_client.generation += 1
                        elif change == 'navigation':
                            host.navigation_generation += 1
                        elif change == 'selector':
                            host.cloud_remote = SimpleNamespace(items=['Other'], value='Replacement')
                        else:
                            host.active_host = False
                    finally:
                        release.set()
                        await task
                self.assertEqual(selector.value, 'Original')
                host.browser_cloud_location.assert_not_awaited()
                host.show_locations.assert_not_called()

    async def test_lookup_error_from_replaced_connection_does_not_publish_stale_error(self):
        host = self.host()
        controller = LocationsController(locations_host(host))
        async def failed_lookup(*args):
            host.cloud_client = SimpleNamespace(generation=2)
            raise OSError('retired connection failed')
        with patch('mobile.composition.locations.asyncio.to_thread', side_effect=failed_lookup):
            await controller.pinned_opener(dict(kind='remote', connection='a' * 64, path='books'))()
        host.show_locations.assert_not_called()
        host.browser_cloud_location.assert_not_awaited()

    async def test_remote_pin_respects_host_window_boundary_before_constructing_cloud_owner(self):
        host = self.host()
        host.show_cloud = Mock(return_value=False)
        host.cloud_controller = Mock(return_value=host)
        controller = LocationsController(locations_host(host))
        await controller.pinned_opener(dict(kind='remote', connection='a' * 64, path='books'))()
        host.show_cloud.assert_called_once()
        host.cloud_controller.assert_not_called()
        host.browser_cloud_location.assert_not_awaited()
        host.show_locations.assert_not_called()

    async def test_local_pin_stops_when_the_host_denies_or_retires_navigation(self):
        for state in ('denied', 'retired'):
            with self.subTest(state=state):
                host = self.host()
                if state == 'denied':
                    host.show_local_location.return_value = False
                else:
                    async def retire():
                        host.active_host = False
                    host.show_local_location.side_effect = retire
                controller = LocationsController(locations_host(host))
                await controller.pinned_opener(dict(kind='local', path='notes'))()
                host.browser_file_location.assert_not_awaited()
                host.show_locations.assert_not_called()

    async def test_secondary_window_routes_explicitly_deny_local_and_remote_navigation(self):
        from mobile.window_scenes import workspace_class
        workspace = workspace_class()
        host = SimpleNamespace(show_window_boundary=Mock())
        self.assertFalse(workspace.show_cloud(host))
        self.assertFalse(await workspace.show_local_location(host))
        self.assertEqual(host.show_window_boundary.call_count, 2)

    async def test_cancelling_a_pinned_open_does_not_cancel_shared_credential_restore(self):
        host = self.host()
        started, release = asyncio.Event(), asyncio.Event()
        async def restore():
            started.set()
            await release.wait()
        shared = host.cloud_restore_task = asyncio.create_task(restore())
        controller = LocationsController(locations_host(host))
        opening = asyncio.create_task(controller.pinned_opener(
            dict(kind='remote', connection='a' * 64, path='books'))())
        try:
            await started.wait()
            await asyncio.sleep(0)
            opening.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await opening
            self.assertFalse(shared.cancelled(), 'one navigation cancelled the process credential restore')
            release.set()
            await shared
            host.browser_cloud_location.assert_not_awaited()
        finally:
            release.set()
            opening.cancel()
            await asyncio.gather(opening, shared, return_exceptions=True)
