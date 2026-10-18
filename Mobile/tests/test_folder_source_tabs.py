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
        self.assertEqual(list(app.folder_source_actions.children), [])
        app.transfer_busy = True
        app.refresh_transfer_status()
        self.assertEqual(list(app.folder_source_actions.children), [app.folder_transfers_button])
        self.assertIsNone(app.folder_add_share_button.parent)
        self.assertEqual(app.folder_source_actions.style.margin_bottom, 12)
        app.transfer_busy = False
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
        self.assertEqual(list(app.folder_source_actions.children), [])
        self.assertIsNone(app.folder_add_share_button.parent)
        self.assertIn(app.folder_credential_row, app.folder_picker_header.children)

    def test_loaded_network_share_packages_never_enter_cloud_credential_filter(self):
        from types import SimpleNamespace
        app = self.app
        app.cloud_client = SimpleNamespace(cancel=lambda: None, package_records=[
            dict(package_name='Network shares', remotes=['Mac']),
            dict(package_name='Session network shares', remotes=['NAS']),
            dict(package_name='Personal.zip', remotes=['Drive']),
        ])
        app.cloud_remote.items = ['Mac', 'NAS', 'Drive']
        app.change_folder_source('rclone')
        self.assertEqual(set(app.folder_credentials), {'All', 'Personal'})
        self.assertEqual(set(app.folder_buttons), {'Drive'})

    def test_browsable_siblings_use_list_titles_and_groups_use_plain_headings(self):
        app = self.app
        names = ['Server-Lib-Books', 'Server-Perforce', 'Server-Perforce-2']
        choices = {}
        for name in names:
            copy = dict(name=name, source='Remote', kind='remote', value=(name, ''), remote=name)
            choices[name] = dict(copy, copies=[copy])
        app.folder_source = 'rclone'
        app.update_folder_list(choices)
        group = app.folder_tree_buttons[('Server', 'Lib')]
        folder = app.folder_buttons['Server-Perforce']
        self.assertEqual(group.style.font_size, folder.style.font_size)
        self.assertEqual(group.style.font_weight, 'bold')
        self.assertEqual(folder.style.font_weight, 'normal')
        self.assertEqual(group.parent.style.height, folder.parent.style.height)
        self.assertEqual(group._impl._surface_roles[1], 'text')
        self.assertEqual(folder._impl._surface_roles[1], 'text')
        for heading in app.folder_tree_buttons.values():
            self.assertEqual(list(heading.parent.children), [heading])
            self.assertEqual(heading._impl._surface_roles[1], 'text')
        self.assertFalse(hasattr(group, 'on_press'))
        self.assertEqual([child.control_icon for child in folder.parent.children
                          if hasattr(child, 'control_icon')], ['folder', 'more'])

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
        self.assertEqual(app.file_source_buttons['Shared files'].text, 'Shared with Files')
        self.assertIsNone(app.file_storage.parent)
        self.assertEqual(app.file_source_buttons['Shared files'].style.font_weight, 'bold')
        app.file_source_buttons['Local files'].on_press()
        app.loop.run_until_complete(__import__('asyncio').sleep(0.05))
        self.assertEqual(app.file_provider.root, documents / 'Local')
        self.assertEqual(app.file_source_buttons['Local files'].style.font_weight, 'bold')
        app.file_source_buttons['Shared files'].on_press()
        app.loop.run_until_complete(__import__('asyncio').sleep(0.05))
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
                    if getattr(child, 'control_icon', '').startswith('folder')]

        self.assertEqual(icons(local['target']), ['folder'])
        self.assertEqual(icons(crypt['target']), ['folder_unlocked'])
        self.assertEqual(icons('Notes'), ['folder'])
        self.assertEqual(icons('All files'), ['folder'])
        app.change_folder_source('rclone')
        self.assertEqual(icons('Online'), ['folder'])
        self.assertEqual(icons(local['target']), ['folder'])
        self.assertEqual(icons(crypt['target']), ['folder_unlocked'])
        store.target(crypt).rename(store.target(crypt).with_name('unmapped'))
        app.show_locations()
        self.assertEqual(icons('Secret'), ['folder_unlocked'])
        app.change_folder_source('Local')
        self.assertNotIn('Secret', app.folder_buttons)

    def test_sibling_encrypted_folders_have_independent_icon_state_and_accessible_names(self):
        from unittest.mock import patch
        app = self.app
        names = ['Server-LLib-Books', 'Server-LLib-Comics']
        choices = {}
        for name in names:
            copy = dict(name=name, source='Remote', kind='remote', value=(name, ''), remote=name)
            choices[name] = dict(copy, copies=[copy])
        app.cloud_crypt_remotes = set(names)
        app.folder_source = 'rclone'
        with patch.object(app, 'loaded_remote_names', return_value=[names[0]]):
            app.update_folder_list(choices)
        for name, expected in zip(names, ['folder_unlocked', 'folder_locked']):
            button = app.folder_buttons[name]
            self.assertEqual(button.parent.children[0].control_icon, expected)
            self.assertEqual(button.parent.children[0]._impl._surface_roles[1], expected)
            self.assertIn(expected.removeprefix('folder_'), button.accessible_name)
        self.assertFalse(hasattr(app.folder_tree_buttons[('Server', 'LLib')], 'on_press'))
        self.assertEqual([b.text for b in app.folder_source_buttons.values()], ['Local', 'Cloud', 'Home Server'])

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
