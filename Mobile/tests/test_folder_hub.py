"""Mobile masks, physical discovery, session associations and transfer destination safety."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch, AsyncMock
from logisticsmobile.folder_hub import hub_entries, visible_remotes
from logisticsmobile.preferences import Preferences
from logisticsmobile.mirror_jobs import MirrorJobs
from test_mirror_jobs import MirrorClient


class FolderHubTests(unittest.TestCase):
    def test_picker_uses_loaded_remote_values_and_opens_selected_local_folder(self):
        from logisticsmobile.app import LogisticsMobile
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                app.show_cloud(present=False)
                root = app.private_root / 'LocalFiles' / 'Comics'
                root.mkdir(parents=True)
                app.cloud_remote.items = ['Loaded drive']
                app.show_locations()
                self.assertIn('Loaded drive', app.folder_picker_choices)
                app.cloud_remote.items = ['Loaded drive', 'Restored later']
                app.set_cloud_busy(False)
                self.assertIn('Restored later', app.folder_picker_choices)
                self.assertFalse(app.routes.screens['files'])
                self.assertIn('Comics', app.folder_picker_choices)
                app.folder_choice.value = 'Comics'
                self.assertEqual(app.routes.screens['files'][-1][0], 'folder-options')
                app.loop.run_until_complete(app.folder_browse_button.on_press())
                self.assertEqual(app.file_path, 'Comics')
                self.assertEqual(app.file_provider.root, app.private_root / 'LocalFiles')
                from unittest.mock import PropertyMock
                with patch.object(type(app.file_storage), 'value', new_callable=PropertyMock, side_effect=IndexError):
                    self.assertIsNone(app.change_file_storage())
            finally:
                app.main_window.close()
                app.loop.close()

    def test_grouped_copies_stay_visible_while_busy_and_actions_recover(self):
        from logisticsmobile.app import LogisticsMobile
        class Client(MirrorClient):
            def crypt_remotes(self): return []
            def cancel(self): pass
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                app.cloud_client = Client()
                app.show_cloud(present=False)
                local, _ = app.mirror_store().create(app.cloud_client, 'Remote', '')
                crypt, _ = app.mirror_store().create(app.cloud_client, 'Secret', '')
                app.cloud_remote.items = ['Remote', 'Secret']
                app.show_locations()
                before = app.folder_picker_choices
                self.assertEqual(len(before['Remote']['copies']), 2)
                self.assertEqual(len(before['Secret']['copies']), 2)
                self.assertEqual(before['Secret']['kind'], 'job')
                self.assertEqual(before['Secret']['source'], 'LocalCrypt')
                app.transfer_busy = True
                app.set_cloud_busy(True)
                app.show_locations()
                self.assertEqual(set(before), set(app.folder_picker_choices))
                app.folder_choice.value = 'Remote'
                self.assertTrue(app.folder_browse_button.enabled)
                self.assertTrue(all(not button.enabled for button, idle in app.folder_action_controls if idle))
                app.loop.run_until_complete(app.folder_browse_button.on_press())
                self.assertEqual(app.file_path, local['target'])
                cancel = app._crypt_cancel
                app.show_locations()
                app.folder_choice.value = 'Secret'
                self.assertFalse(app.folder_browse_button.enabled)
                self.assertFalse(app.loop.run_until_complete(app.open_picker_folder(app.folder_picker_selected)))
                self.assertIs(app._crypt_cancel, cancel)
                app.transfer_busy = False
                app.set_cloud_busy(False)
                self.assertTrue(app.folder_browse_button.enabled)
                app.show_home()
                app.select_destination('files')
                self.assertFalse(app.routes.screens['files'])
                self.assertEqual(set(before), set(app.folder_picker_choices))
                self.assertTrue(app.mirror_store().target(crypt).exists())
            finally:
                app.main_window.close()
                app.loop.close()

    def test_unmapped_local_delete_requires_confirmation_and_keeps_siblings(self):
        from logisticsmobile.app import LogisticsMobile
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                app.show_cloud(present=False)
                folder = app.private_root / 'LocalFiles' / 'Comics'
                folder.mkdir(parents=True)
                (folder / 'note.txt').write_text('keep until confirmed')
                sibling = folder.parent / 'Other'
                sibling.mkdir()
                app.show_locations()
                entry = app.folder_picker_choices['Comics']
                app.show_picker_folder(entry)
                async def exercise():
                    with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=False)):
                        with patch('commonUtils.runtime.resource_mutations.inventory', side_effect=AssertionError('No pre-confirmation scan')):
                            self.assertFalse(await app.delete_picker_folder(entry))
                        self.assertTrue(folder.exists())
                    async def confirm(*args, **kwargs):
                        (folder / 'added-while-confirming').write_text('delete too')
                        return True
                    with patch.object(app.main_window, 'dialog', new=confirm):
                        with patch('commonUtils.runtime.resource_mutations.inventory', side_effect=AssertionError('No inventory')):
                            self.assertTrue(await app.delete_picker_folder(entry))
                    self.assertFalse(folder.exists())
                    self.assertTrue(sibling.exists())
                app.loop.run_until_complete(exercise())
            finally:
                app.main_window.close()
                app.loop.close()

    def test_mapped_local_and_localcrypt_confirm_before_scanning_and_wipe_new_contents(self):
        from logisticsmobile.app import LogisticsMobile
        class Client(MirrorClient):
            def crypt_remotes(self): return []
            def cancel(self): pass
        for remote in ('Remote', 'Secret'):
            with self.subTest(remote=remote), TemporaryDirectory() as directory:
                LogisticsMobile.storage_root = Path(directory)
                app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
                try:
                    app.cloud_client = Client()
                    app.show_cloud(present=False)
                    store = app.mirror_store()
                    job, _ = store.create(app.cloud_client, remote, 'folder')
                    target = store.target(job)
                    app.show_transfers()
                    async def confirm(*args, **kwargs):
                        self.assertTrue(target.exists())
                        (target / 'new-content').write_text('wipe all contents')
                        return True
                    async def exercise():
                        with (patch.object(app.main_window, 'dialog', new=confirm),
                              patch.object(store, 'state', side_effect=AssertionError('No tree inspection')),
                              patch('commonUtils.runtime.resource_mutations.inventory', side_effect=AssertionError('No inventory'))):
                            self.assertTrue(await app.delete_mirror_copy(job['id']))
                    app.loop.run_until_complete(exercise())
                    self.assertFalse(target.exists())
                    self.assertNotIn(job['id'], MirrorJobs(directory).jobs)
                finally:
                    app.main_window.close()
                    app.loop.close()
                    LogisticsMobile.storage_root = None

    def test_ini_is_authoritative_and_discovery_never_creates_remote_folders(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'LocalFiles' / 'Games-NES').mkdir(parents=True)
            (root / 'LocalFiles' / 'Games-PMSDATA').mkdir()
            (root / 'LocalFiles' / 'Dropbox').mkdir()
            rows = hub_entries(root, {}, ['Dropbox', 'Games-NES', 'Games-SNES', 'Games-PMSDATA'])
            self.assertEqual([row[0] for row in rows], ['Dropbox', 'Games-NES', 'Games-SNES'])
            nes = rows[1]
            self.assertEqual(nes[1], ('Games', 'NES'))
            self.assertEqual([copy[0] for copy in nes[2]], ['Local', 'Remote'])
            self.assertFalse((root / 'LocalCryptFolders').exists())
            with patch('logisticsmobile.folder_hub.exclusions', return_value=(frozenset({'other'}), ('-extra',))):
                self.assertEqual(visible_remotes(['Dropbox', 'other', 'Hello-extra']), ['Dropbox'])

    def test_only_existing_crypt_jobs_are_local_and_session_names_survive_restart(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store, client = MirrorJobs(root), MirrorClient()
            job, _ = store.create(client, 'Secret', 'private title')
            rows = hub_entries(root, store.jobs, ['Secret'])
            self.assertEqual([kind for kind, _ in rows[0][2]], ['LocalCrypt', 'Remote'])
            (store.target(job) / 'opaque-name').unlink()
            store.target(job).rmdir()
            self.assertEqual([kind for kind, _ in hub_entries(root, store.jobs, ['Secret'])[0][2]], ['Remote'])
            preferences = Preferences(root)
            preferences.save(remote_packages=json.dumps([dict(zip='credentials.zip', remotes=['Secret'], session_only=True)]))
            restored = Preferences(root)
            self.assertEqual(json.loads(restored.values['remote_packages'])[0]['zip'], 'credentials.zip')
            self.assertNotIn('password', restored.path.read_text())

    def test_adopt_existing_local_folder_syncs_and_reuses_mapping(self):
        with TemporaryDirectory() as directory:
            store, client = MirrorJobs(directory), MirrorClient()
            target = Path(directory) / 'LocalFiles' / 'folder'
            target.mkdir(parents=True)
            (target / 'note.txt').write_bytes(b'existing edit')
            job, (status, snapshot) = store.create(client, 'Remote', 'folder', storage='Local')
            self.assertEqual(store.target(job), target)
            self.assertEqual(status, 'updated')
            self.assertEqual((target / 'note.txt').read_bytes(), b'first')
            self.assertIsNone(snapshot)
            self.assertNotIn('snapshots', job)
            repeated, _ = store.create(client, 'Remote', 'folder', storage='Local')
            self.assertEqual(repeated['id'], job['id'])
            self.assertEqual(len(store.jobs), 1)
            with self.assertRaisesRegex(ValueError, 'crypt remote'):
                store.create(client, 'Remote', 'folder', storage='LocalCrypt')

    def test_destination_chooser_existing_default_and_confirmed_local_deletion(self):
        from logisticsmobile.app import LogisticsMobile
        class Client(MirrorClient):
            def crypt_remotes(self): return []
            def cancel(self): pass
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                app.cloud_client = Client()
                app.show_cloud(present=False)
                app.cloud_remote.items = ['Remote']
                app.cloud_remote.value = app.cloud_open_remote = 'Remote'
                app.cloud_path = 'folder'
                async def exercise():
                    await app.pull_remote_copy()
                    self.assertEqual(app.routes.screens['files'][-1][0], 'pull-destination')
                    store = app.mirror_store()
                    pull_here = app.body.children[0].children[2].on_press
                    with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=False)):
                        pull_here()
                        self.assertFalse(await app.transfer_task)
                        self.assertEqual(store.jobs, {})
                    with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)):
                        pull_here()
                        self.assertTrue(await app.transfer_task)
                    job = next(iter(store.jobs.values()))
                    with patch.object(app, 'start_mirror_pull') as pull:
                        await app.pull_remote_copy()
                        pull.assert_called_once_with(job['id'])
                    app.show_transfers()
                    with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=False)):
                        self.assertFalse(await app.delete_mirror_copy(job['id']))
                    self.assertTrue(store.target(job).exists())
                    with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)):
                        self.assertTrue(await app.delete_mirror_copy(job['id']))
                    self.assertFalse(store.target(job).exists())
                    self.assertNotIn(job['id'], MirrorJobs(directory).jobs)
                    self.assertEqual(app.cloud_client.data['folder/note.txt'], b'first')
                app.loop.run_until_complete(exercise())
            finally:
                app.main_window.close()
                app.loop.close()
