"""Source isolation, credential defaults and iOS shared-root browsing."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from logisticsmobile.app import LogisticsMobile
from features.rclone.mobile.storage_location import use_shared_local, _shared_local_roots


class FolderSourceTabTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        LogisticsMobile.storage_root = Path(self.directory.name) / 'private'
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.app.show_cloud(present=False)

    def tearDown(self):
        _shared_local_roots.pop(self.app.private_root, None)
        self.app.main_window.close()
        self.app.loop.close()
        LogisticsMobile.storage_root = None
        self.directory.cleanup()

    def test_tabs_isolate_sources_and_reset_rclone_credential(self):
        app = self.app
        app.cloud_remote.items = ['Personal drive', 'Work drive', 'Home Mac']
        app.remember_credential_association('Personal.zip', ['Personal drive'], session_only=True)
        app.remember_credential_association('Work.zip', ['Work drive'], session_only=True)
        app.remember_credential_association('Session network shares', ['Home Mac'], session_only=True)
        (app.private_root / 'LocalFiles' / 'Notes').mkdir(parents=True)
        app.show_locations()
        self.assertEqual(app.folder_source, 'Local')
        self.assertEqual(set(app.folder_buttons), {'All files', 'Notes'})
        app.change_folder_source('rclone')
        self.assertEqual(set(app.folder_buttons), {'Personal drive', 'Work drive'})
        self.assertEqual(set(app.folder_credentials), {'All', 'Personal', 'Work'})
        app.folder_credential.value = 'Personal'
        self.assertEqual(set(app.folder_buttons), {'Personal drive'})
        app.folder_source_buttons['rclone'].on_press()
        self.assertEqual(app.folder_credential.value, 'Personal')
        app.folder_source_buttons['Local'].on_press()
        self.assertEqual(set(app.folder_buttons), {'All files', 'Notes'})
        self.assertFalse(app.folder_picker_header.children)
        app.folder_source_buttons['Network shares'].on_press()
        self.assertEqual(set(app.folder_buttons), {'Home Mac'})
        self.assertFalse(app.folder_picker_header.children)
        app.show_locations()
        self.assertEqual(app.folder_source, 'Network shares')
        app.folder_source_buttons['rclone'].on_press()
        self.assertEqual(app.folder_credential.value, 'All')
        self.assertEqual(set(app.folder_buttons), {'Personal drive', 'Work drive'})
        self.assertIs(app.folder_picker_header.children[0], app.folder_credential_row)

    def test_source_actions_follow_tab_without_leaving_empty_toolbar_or_duplicate_share(self):
        app = self.app
        app.show_locations()
        self.assertEqual(list(app.folder_source_actions.children), [])
        app.change_folder_source('rclone')
        self.assertEqual(list(app.folder_source_actions.children), [app.folder_transfers_button])
        self.assertIsNone(app.folder_add_share_button.parent)
        self.assertEqual(app.folder_source_actions.style.margin_bottom, 12)
        app.change_folder_source('Local')
        self.assertEqual(list(app.folder_source_actions.children), [])
        self.assertEqual(app.folder_source_actions.style.margin_bottom, 0)
        self.assertIsNone(app.folder_transfers_button.parent)
        self.assertIsNone(app.folder_add_share_button.parent)
        app.change_folder_source('Network shares')
        self.assertEqual(list(app.folder_source_actions.children), [app.folder_add_share_button])
        self.assertIsNone(app.folder_transfers_button.parent)
        self.assertFalse(app.folder_picker_header.children)
        self.assertFalse(any(getattr(child, 'text', '') == 'Add share…'
                             for child in app.folder_list.children))
        app.show_locations()
        self.assertEqual(list(app.folder_source_actions.children), [app.folder_add_share_button])
        app.change_folder_source('rclone')
        self.assertEqual(list(app.folder_source_actions.children), [app.folder_transfers_button])
        self.assertIsNone(app.folder_add_share_button.parent)
        self.assertIn(app.folder_credential_row, app.folder_picker_header.children)

    def test_ios_local_tab_opens_files_beside_local_and_other_subfolders(self):
        app = self.app
        documents = Path(self.directory.name) / 'Documents'
        (documents / 'Local' / 'Managed').mkdir(parents=True)
        (documents / 'Notes').mkdir()
        (documents / 'note.md').write_text('# Shared root')
        (documents / 'Notes' / 'nested.txt').write_text('Nested file')
        use_shared_local(app.private_root, documents)
        app.show_locations()
        app.change_folder_source('Local')
        self.assertEqual(set(app.folder_buttons), {'All files', 'Notes'})
        app.loop.run_until_complete(app.folder_buttons['All files'].on_press())
        self.assertEqual(app.file_provider.root, documents)
        self.assertEqual({row['name'] for row in app.file_rows.values()}, {'Notes', 'note.md'})
        with self.assertRaises(ValueError):
            app.file_provider.entry('Local/Managed')
        app.show_locations()
        app.loop.run_until_complete(app.folder_buttons['Notes'].on_press())
        self.assertEqual(app.file_path, 'Notes')
        self.assertEqual({row['name'] for row in app.file_rows.values()}, {'nested.txt'})

    def test_mapped_copies_also_appear_locally(self):
        from logisticsmobile.folder_hub import source_choices
        choices = {'Offline': dict(source='Local', kind='job', remote='Drive', copies=[
            dict(source='Local', remote='Drive'), dict(source='Remote', remote='Drive')]),
            'Share copy': dict(source='Local', kind='job', remote='Mac', copies=[])}
        self.assertEqual(set(source_choices(choices, 'rclone', {'Mac'})), {'Offline'})
        self.assertEqual(set(source_choices(choices, 'Network shares', {'Mac'})), {'Share copy'})
        self.assertEqual(set(source_choices(choices, 'Local', {'Mac'})), {'Offline', 'Share copy'})

    def test_rows_show_storage_for_selected_tab(self):
        from test_mirror_jobs import MirrorClient
        class Client(MirrorClient):
            def cancel(self): pass
        app = self.app
        app.cloud_client = Client()
        app.cloud_remote.items = ['Remote', 'Secret', 'Online']
        store = app.mirror_store()
        local, _ = store.create(app.cloud_client, 'Remote', 'folder', storage='Local')
        crypt, _ = store.create(app.cloud_client, 'Secret', 'folder', storage='LocalCrypt')
        (app.private_root / 'LocalFiles' / 'Notes').mkdir(parents=True)
        app.cloud_crypt_remotes = {'Secret'}
        app.show_locations()
        self.assertNotIn('Online', app.folder_buttons)

        def icons(name):
            return [child.control_icon for child in app.folder_buttons[name].parent.children
                    if getattr(child, 'control_icon', '').startswith('storage_')]

        self.assertEqual(icons(local['target']), ['storage_local'])
        self.assertEqual(icons(crypt['target']), ['storage_crypt'])
        self.assertEqual(icons('Notes'), ['storage_local'])
        self.assertEqual(icons('All files'), ['storage_local'])
        app.change_folder_source('rclone')
        self.assertEqual(icons('Online'), ['storage_remote'])
        self.assertEqual(icons(local['target']), ['storage_remote'])
        self.assertEqual(icons(crypt['target']), ['storage_crypt'])
        store.target(crypt).rename(store.target(crypt).with_name('unmapped'))
        app.show_locations()
        self.assertEqual(icons('Secret'), ['storage_crypt'])
        app.change_folder_source('Local')
        self.assertNotIn('Secret', app.folder_buttons)

    def test_tab_taps_open_matching_copy_and_menus_keep_same_mapping_actions(self):
        from unittest.mock import AsyncMock, patch
        from test_mirror_jobs import MirrorClient
        app = self.app
        class Client(MirrorClient):
            def cancel(self): pass
        app.cloud_client = Client()
        app.cloud_remote.items = ['Remote', 'Secret']
        store = app.mirror_store()
        jobs = [store.create(app.cloud_client, remote, 'folder', storage=storage)[0]
                for remote, storage in [('Remote', 'Local'), ('Secret', 'LocalCrypt')]]
        app.show_locations()
        for job in jobs:
            menus = []
            for tab, expected in [('Local', 'job'), ('rclone', 'job-remote')]:
                app.change_folder_source(tab)
                name = job['target']
                with patch.object(app, 'open_picker_folder', new=AsyncMock(return_value=True)) as opened:
                    app.loop.run_until_complete(app.folder_buttons[name].on_press())
                    target = opened.call_args.args[0]
                    self.assertEqual(target['kind'], expected)
                    self.assertEqual(target['value'], job['id'])
                menu = next(child for child in app.folder_buttons[name].parent.children
                            if getattr(child, 'control_icon', '') == 'more')
                menu.on_press()
                controls = [button.text for button, _ in app.folder_action_controls]
                self.assertIn('Pull…', controls)
                self.assertIn('Push…', controls)
                self.assertIn('Browse Remote', controls)
                self.assertIn('Delete local folder…', controls)
                menus.append(controls)
            self.assertEqual(*menus)
