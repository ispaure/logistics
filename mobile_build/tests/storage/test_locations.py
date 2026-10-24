from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from mobile.locations import Locations
from mobile.locations_controller import LocationsController
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


class PinnedNavigationTests(unittest.IsolatedAsyncioTestCase):
    def host(self):
        client = SimpleNamespace(generation=1, connection_identity=Mock(return_value='a' * 64))
        return SimpleNamespace(active_host=True, cloud_client=client,
            cloud_remote=SimpleNamespace(items=['Public', 'Encrypted'], value='Original'),
            cloud_crypt_remotes={'Encrypted'}, cloud_restore_task=None,
            show_cloud=Mock(), show_locations=Mock(), browser_cloud_location=AsyncMock())

    async def test_current_connection_opens_matching_ordinary_folder(self):
        host = self.host()
        controller = LocationsController(host)
        await controller.pinned_opener(dict(kind='remote', connection='a' * 64, path='books'))()
        host.cloud_client.connection_identity.assert_called_once_with('Public')
        host.browser_cloud_location.assert_awaited_once_with(('Public', 'books'))
        self.assertEqual(host.cloud_remote.value, 'Public')
        host.show_locations.assert_not_called()

    async def test_replaced_or_retired_connection_cannot_navigate_after_lookup(self):
        for change in ('client', 'generation', 'selector', 'inactive'):
            with self.subTest(change=change):
                host = self.host()
                selector = host.cloud_remote
                controller = LocationsController(host)
                started, release = asyncio.Event(), asyncio.Event()
                async def lookup(*args):
                    started.set()
                    await release.wait()
                    return 'a' * 64
                with patch('mobile.locations_ui.asyncio.to_thread', side_effect=lookup):
                    task = asyncio.create_task(controller.pinned_opener(
                        dict(kind='remote', connection='a' * 64, path='books'))())
                    try:
                        await asyncio.wait_for(started.wait(), 1)
                        if change == 'client':
                            host.cloud_client = SimpleNamespace(generation=1)
                        elif change == 'generation':
                            host.cloud_client.generation += 1
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
        controller = LocationsController(host)
        async def failed_lookup(*args):
            host.cloud_client = SimpleNamespace(generation=2)
            raise OSError('retired connection failed')
        with patch('mobile.locations_ui.asyncio.to_thread', side_effect=failed_lookup):
            await controller.pinned_opener(dict(kind='remote', connection='a' * 64, path='books'))()
        host.show_locations.assert_not_called()
        host.browser_cloud_location.assert_not_awaited()
