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
    def folder_app(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        LogisticsMobile.storage_root = Path(directory.name)
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(app.loop.close)
        self.addCleanup(app.main_window.close)
        app.show_cloud(present=False)
        return app

    def test_source_round_trip_reuses_native_rows_and_renders_once(self):
        app = self.folder_app()
        app.cloud_remote.items = ['Drive', 'Mac']
        app.remember_credential_association('Personal.zip', ['Drive'], session_only=True)
        app.remember_credential_association('Session network shares', ['Mac'], session_only=True)
        app.show_locations()
        local = app.folder_buttons['All files']
        app.change_folder_source('rclone')
        cloud = app.folder_buttons['Drive']
        app.folder_credential.value = 'Personal'
        with patch.object(app, 'update_folder_list', wraps=app.update_folder_list) as render:
            app.change_folder_source('Network shares')
            self.assertEqual(render.call_count, 1)
        server = app.folder_buttons['Mac']
        for source, name, button in [('Local', 'All files', local),
                                      ('rclone', 'Drive', cloud),
                                      ('Network shares', 'Mac', server)]:
            app.change_folder_source(source)
            self.assertIs(app.folder_buttons[name], button)
        self.assertLessEqual(len(app.folder_tab_views), 3)

    def test_tab_cache_invalidates_after_local_and_credential_changes(self):
        app = self.folder_app()
        app.cloud_remote.items = ['Secret']
        app.cloud_crypt_remotes = {'Secret'}
        app.show_locations()
        app.change_folder_source('rclone')
        unlocked = app.folder_buttons['Secret']
        self.assertIn('unlocked', unlocked.accessible_name)
        app.change_folder_source('Local')
        (app.private_root / 'LocalFiles' / 'New folder').mkdir(parents=True)
        app.change_folder_source('rclone')
        app.change_folder_source('Local')
        self.assertIn('New folder', app.folder_buttons)
        app.remember_credential_association('Personal.zip', ['Secret'], session_only=True)
        retained = patch.object(app, 'retained_credential_associations', return_value=[
            dict(zip='Personal.zip', remotes=['Secret'], crypt_remotes=['Secret'])])
        retained.start()
        self.addCleanup(retained.stop)
        app.cloud_remote.items = []
        app.change_folder_source('rclone')
        locked = app.folder_buttons['Secret']
        self.assertIsNot(locked, unlocked)
        self.assertIn('locked', locked.accessible_name)
        self.assertNotIn('unlocked', locked.accessible_name)
        # A changed mapping may reuse its original dict; cache keys must own a
        # snapshot rather than compare the same, now-mutated object to itself.
        choices = app.folder_picker_choices
        choices['Secret']['name'] = 'Renamed'
        app.update_folder_list(choices)
        self.assertIsNot(app.folder_buttons['Secret'], locked)

    def test_large_encrypted_tab_reads_credential_state_a_constant_number_of_times(self):
        app = self.folder_app()
        names = [f'Server-Library-{index}' for index in range(120)]
        app.cloud_remote.items = names
        app.cloud_crypt_remotes = set(names)
        app.show_locations()
        choices = app.folder_picker_choices
        app.folder_source = 'rclone'
        with patch.object(app, 'loaded_remote_names', wraps=app.loaded_remote_names) as loaded, patch.object(
                app, 'retained_credential_associations', wraps=app.retained_credential_associations) as retained:
            app.update_folder_list(choices)
            self.assertEqual(len(app.folder_buttons), 120)
            self.assertEqual(loaded.call_count, 1)
            self.assertLessEqual(retained.call_count, 3)
        with patch('logisticsmobile.folder_hub_ui.toga.Button', side_effect=AssertionError('Rebuilt tab')):
            app.update_folder_list(choices)

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
        from contextlib import nullcontext
        host = SimpleNamespace(active_host=True, cloud_client=SimpleNamespace(generation=1),
            file_browser=SimpleNamespace(population_paused=nullcontext),
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
                    self.assertEqual(app.file_status.value, '')
                    header = app.file_browser.location_bar
                    self.assertEqual(header.caption.children, [header.folder_name, header.storage_identity])
                    busy.assert_not_called()
                    downloads.assert_not_called()
                    release.set()
                    await app.file_browser.close()
            try:
                app.loop.run_until_complete(check())
            finally:
                app.main_window.close()
                app.loop.close()
