"""Navigation work stays bounded without weakening local resource boundaries."""
import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from features.rclone.mobile.storage_location import CollectionFiles
from features.rclone.localcrypt.mobile.resources import CryptFiles
from commonUtils.runtime.operations import OperationCancelled
from commonUtils.runtime.local_files import LocalFiles
from logisticsmobile.app import LogisticsMobile


class FolderNavigationTests(unittest.TestCase):
    def test_collection_snapshot_matches_rows_with_constant_location_checks(self):
        with TemporaryDirectory() as root:
            provider = CollectionFiles(root)
            (provider.root / 'folder').mkdir()
            for index in range(120):
                (provider.root / f'{index}.txt').write_text(str(index))
            expected = LocalFiles.list(provider)
            from features.rclone.mobile import storage_location
            with patch.object(storage_location, 'collection_path', wraps=storage_location.collection_path) as locate:
                self.assertEqual(provider.list(), expected)
                self.assertLessEqual(locate.call_count, 3)

    def test_collection_listing_rejects_linked_files_and_checks_cancellation(self):
        with TemporaryDirectory() as root:
            provider = CollectionFiles(root)
            target = provider.root / 'original.txt'
            target.write_text('test')
            linked = provider.root / 'link.txt'
            for make in (lambda: linked.symlink_to(target), lambda: os.link(target, linked)):
                make()
                with self.assertRaises(ValueError):
                    provider.list()
                linked.unlink()
            with self.assertRaises(OperationCancelled):
                provider.list(cancelled=lambda: True)

    def test_collection_listing_respects_nested_protected_roots(self):
        from commonUtils.filesystem.local_access import protect_local_root
        with TemporaryDirectory() as root:
            provider = CollectionFiles(root)
            protected = provider.root / 'private'
            protected.mkdir()
            release = protect_local_root(self, protected, 'Private resource')
            try:
                with self.assertRaisesRegex(PermissionError, 'Private resource'):
                    provider.list()
            finally:
                release()

    def test_localcrypt_names_cross_native_boundary_in_bounded_batches(self):
        class Client:
            def __init__(self):
                self.batches = []
            def request(self, action, **values):
                if action == 'crypt_path':
                    return dict(identity='a' * 64, path=values['path'])
                if action == 'crypt_paths':
                    self.batches.append(values['entries'])
                    return [item['path'] for item in values['entries']]
                raise AssertionError(action)
        with TemporaryDirectory() as root:
            client = Client()
            provider = CryptFiles(root, client, 'Secret')
            for index in range(600):
                (provider.root / f'{index}.txt').write_text('ciphertext fixture')
            (provider.root / 'unfinished.12345678.partial').write_text('partial')
            rows = provider.list()
            self.assertEqual(len(rows), 600)
            self.assertEqual([len(batch) for batch in client.batches], [256, 256, 88])
            self.assertTrue(all(row['revision'] for row in rows))

    def test_private_listing_rejects_replaced_client_even_with_same_generation(self):
        from logisticsmobile.files_ui import FilesUI
        host = SimpleNamespace(active_host=True, cloud_client=SimpleNamespace(generation=1),
            file_storage=SimpleNamespace(value='Private'), file_location=SimpleNamespace(value=''),
            populate_file_browser=Mock())
        def listing(*args, **kwargs):
            host.cloud_client = SimpleNamespace(generation=1)
            return []
        provider = SimpleNamespace(private=True, relative=lambda path: path, list=listing)
        host.file_provider_for = lambda label: provider
        self.assertFalse(asyncio.run(FilesUI.browse_local_during_transfer(host, '')))
        host.populate_file_browser.assert_not_called()

    def test_navigation_does_not_refresh_global_ui_or_wait_for_thumbnails(self):
        with TemporaryDirectory() as root:
            LogisticsMobile.storage_root = Path(root)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            async def check():
                app.show_cloud(present=False)
                await app.show_files()
                folder = app.file_provider.root / 'books'
                folder.mkdir()
                (folder / 'page.jpg').write_bytes(b'preview fixture')
                app.file_location.value = 'books'
                release = asyncio.Event()
                async def delayed_thumbnail(*args):
                    await release.wait()
                with patch.object(app, 'set_cloud_busy') as busy, patch.object(app, 'refresh_downloads') as downloads, patch.object(
                        app.file_browser, '_load_thumbnail', side_effect=delayed_thumbnail):
                    self.assertTrue(await asyncio.wait_for(app.browse_files(), 2))
                    self.assertEqual(app.file_path, 'books')
                    busy.assert_not_called()
                    downloads.assert_not_called()
                    release.set()
                    await app.file_browser.close()
            try:
                app.loop.run_until_complete(check())
            finally:
                app.main_window.close()
                app.loop.close()
