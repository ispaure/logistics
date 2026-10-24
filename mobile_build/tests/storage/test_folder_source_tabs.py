"""Source isolation, credential defaults and iOS shared-root browsing."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from mobile.app import LogisticsMobile
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
        from types import SimpleNamespace
        app = self.app
        app.cloud_client = SimpleNamespace(generation=0, cancel=lambda: None, package_records=[
            dict(package_name='Personal.zip', remotes=['Personal drive']),
            dict(package_name='Work.zip', remotes=['Work drive']),
            dict(package_name='Session network shares', remotes=['Home Mac'])])
        app.set_loaded_remote_names(['Personal drive', 'Work drive', 'Home Mac'])
        app.remember_credential_association('Personal.zip', ['Personal drive'], session_only=True)
        app.remember_credential_association('Work.zip', ['Work drive'], session_only=True)
        app.remember_credential_association('Session network shares', ['Home Mac'], session_only=True)
        (app.private_root / 'LocalFiles' / 'Notes').mkdir(parents=True)
        app.show_locations()
        self.assertEqual(app.folder_source, 'Local')
        self.assertEqual(set(app.folder_buttons), {'All files', 'Notes', 'Received Files'})
        app.change_folder_source('rclone')
        self.assertEqual(set(app.folder_buttons), {'Personal drive', 'Work drive'})
        self.assertEqual(set(app.folder_credentials), {'All', 'Personal', 'Work'})
        app.folder_credential.value = 'Personal'
        self.assertEqual(set(app.folder_buttons), {'Personal drive'})
        app.folder_source_buttons['rclone'].on_press()
        self.assertEqual(app.folder_credential.value, 'Personal')
        app.folder_source_buttons['Local'].on_press()
        self.assertEqual(set(app.folder_buttons), {'All files', 'Notes', 'Received Files'})
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
        self.assertEqual(list(app.folder_source_actions.children), [app.folder_add_remote_button])
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
        self.assertEqual(list(app.folder_source_actions.children), [app.folder_add_remote_button])
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

    def test_setup_actions_disappear_for_configured_connections_and_return_when_removed(self):
        app = self.app
        app.show_locations()
        app.remember_credential_association('Personal.zip', ['Drive'], session_only=True)
        app.remember_credential_association('Session network shares', ['Mac'], session_only=True)
        app.change_folder_source('Network shares')
        self.assertEqual(list(app.folder_source_actions.children), [])
        self.assertEqual(app.folder_source_actions.style.margin_bottom, 0)
        app.change_folder_source('rclone')
        self.assertEqual(list(app.folder_source_actions.children), [])
        # Filtering every workspace out must not offer to add an existing connection.
        app.update_folder_list({})
        self.assertEqual(list(app.folder_source_actions.children), [])
        app.session_credential_packages = []
        app.update_folder_list(app.folder_choices())
        self.assertEqual(list(app.folder_source_actions.children), [app.folder_add_remote_button])
        app.change_folder_source('Network shares')
        self.assertEqual(list(app.folder_source_actions.children), [app.folder_add_share_button])

    def test_retained_locked_connections_suppress_setup_actions(self):
        from unittest.mock import patch
        app = self.app
        with patch.object(app, 'retained_credential_associations', return_value=[
                dict(zip='Personal.zip', remotes=['Drive']),
                dict(zip='Network shares', remotes=['Mac'])]):
            app.change_folder_source('rclone')
            self.assertEqual(list(app.folder_source_actions.children), [])
            app.change_folder_source('Network shares')
            self.assertEqual(list(app.folder_source_actions.children), [])

    def test_empty_cloud_add_remote_opens_connection_settings(self):
        app = self.app
        app.show_locations()
        app.change_folder_source('rclone')
        app.folder_add_remote_button.on_press()
        self.assertEqual(app.native_host.state.destination, 'settings')
        self.assertEqual(app.routes.screens['settings'][-1][0], 'connections')

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
        # Pinned native backends convert Toga CSS points to native pt/sp.
        self.assertAlmostEqual(folder.style.font_size * 96 / 72, 17, delta=2 / 3)
        self.assertEqual(group.style.font_weight, 'bold')
        self.assertEqual(folder.style.font_weight, 'normal')
        self.assertEqual(group.parent.style.height, folder.parent.style.height)
        self.assertEqual(group._impl._surface_roles[1], 'text')
        self.assertEqual(folder._impl._surface_roles[1], 'text')
        self.assertTrue(folder.parent._impl._surface_eink_outlined)
        self.assertFalse(group._impl._surface_eink_outlined)
        for heading in app.folder_tree_buttons.values():
            self.assertEqual(list(heading.parent.children), [heading])
            self.assertEqual(heading._impl._surface_roles[1], 'text')
        self.assertFalse(hasattr(group, 'on_press'))
        self.assertEqual([child.control_icon for child in folder.parent.children
                          if hasattr(child, 'control_icon')], ['folder', 'more'])
        menu = folder.parent.children[-1]
        self.assertGreaterEqual(folder.parent.children[0].style.width, 48)
        self.assertGreaterEqual(menu.style.width, 48)
        self.assertGreaterEqual(menu.style.height, 48)

    def test_source_controls_keep_full_targets_and_consistent_native_text_size(self):
        app = self.app
        app.show_locations()
        for control in [*app.folder_source_buttons.values(), app.folder_credential,
                        app.folder_transfers_button, app.folder_add_share_button,
                        app.folder_add_remote_button]:
            self.assertGreaterEqual(control.style.height, 48)
            self.assertEqual(control.style.font_size * 96 / 72, 16)

    def test_all_files_local_back_returns_to_shared_root_before_workspaces(self):
        app = self.app
        documents = Path(self.directory.name) / 'Documents'
        (documents / 'Local').mkdir(parents=True)
        (documents / 'note.md').write_text('# Shared root')
        use_shared_local(app.private_root, documents)
        for system_back in (False, True):
            with self.subTest(system_back=system_back):
                app.show_locations()
                overview = app.body
                app.loop.run_until_complete(app.folder_buttons['All files'].on_press())
                browser = app.body
                local = next(row for row in app.file_rows.values() if row['name'] == 'Local')
                app.loop.run_until_complete(app.browser_file_folder(local))
                if system_back:
                    self.assertTrue(app.routes.system_back())
                    app.loop.run_until_complete(app.routes.back_task)
                else:
                    app.loop.run_until_complete(app.parent_file_folder())
                self.assertIs(app.body, browser)
                self.assertEqual(app.file_provider.root, documents)
                self.assertEqual({row['name'] for row in app.file_rows.values()}, {'Local', 'Received Files', 'note.md'})
                if system_back:
                    self.assertTrue(app.routes.system_back())
                else:
                    app.loop.run_until_complete(app.parent_file_folder())
                self.assertIs(app.body, overview)

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
        self.assertEqual(set(app.folder_buttons), {'All files', 'Managed', 'Notes', 'Received Files'})
        self.assertEqual(list(app.folder_buttons)[-1], 'All files')
        self.assertEqual(app.folder_buttons['All files'].text, 'Browse All Files')
        app.loop.run_until_complete(app.folder_buttons['All files'].on_press())
        self.assertEqual(app.file_provider.root, documents)
        self.assertEqual(app.file_source_buttons, {})
        self.assertIsNone(app.file_source_tabs.parent)
        header = app.file_browser.location_bar
        self.assertIs(header.parent.children[0], header)
        self.assertIs(app.file_browser.location_bar.children[-1], app.file_actions_button)
        self.assertEqual(app.file_actions_button.control_icon, 'overflow')
        self.assertIsNone(app.file_storage.parent)
        self.assertEqual({row['name'] for row in app.file_rows.values()}, {'Local', 'Notes', 'Received Files', 'note.md'})
        collection = next(row for row in app.file_rows.values() if row['name'] == 'Local')
        self.assertNotIn('display_name', collection)
        self.assertIn('Local', [row.title for row in app.file_browser.native_list.data])
        app.loop.run_until_complete(app.browser_file_folder(collection))
        self.assertEqual(app.file_provider.root, documents / 'Local')
        self.assertEqual(app.file_browser.location_bar.folder_name.text, 'Local')
        self.assertEqual(app.file_source_buttons, {})
        self.assertEqual(app.file_browser.location_bar.parent_button.control_icon, 'up')
        app.loop.run_until_complete(app.browser_file_folder(next(iter(app.file_rows.values()))))
        self.assertEqual(app.file_path, 'Managed')
        app.loop.run_until_complete(app.parent_file_folder())
        self.assertEqual(app.file_provider.root, documents / 'Local')
        app.loop.run_until_complete(app.parent_file_folder())
        self.assertEqual(app.file_provider.root, documents)
        self.assertEqual(app.file_path, '')
        self.assertEqual(app.file_browser.location_bar.folder_name.text, 'On this device')
        self.assertEqual(app.file_browser.location_bar.parent_button.control_icon, 'back')
        with self.assertRaises(ValueError):
            app.file_provider.entry('Local')
        from commonUtils.search.providers import search_resources
        (documents / 'Local' / 'Managed' / 'find-me.txt').write_text('collection content')
        result = search_resources(app.file_provider, '', 'find-me')
        self.assertTrue(result.complete)
        self.assertEqual([row['path'] for row in result.rows], ['Local/Managed/find-me.txt'])
        app.file_browser.show_tiles()
        self.assertIn('Local', [button.text for button in app.file_browser.buttons.values()])
        app.show_locations()
        app.loop.run_until_complete(app.folder_buttons['Managed'].on_press())
        self.assertEqual(app.file_provider.root, documents / 'Local')
        self.assertEqual(app.file_path, 'Managed')
        app.show_locations()
        app.loop.run_until_complete(app.folder_buttons['Notes'].on_press())
        self.assertEqual(app.file_path, 'Notes')
        self.assertEqual({row['name'] for row in app.file_rows.values()}, {'nested.txt'})

    def test_unified_root_preserves_collection_mutations_pins_and_editor_identity(self):
        from unittest.mock import AsyncMock, patch
        from commonUtils.runtime.resources.mutations import delete_resource
        from mobile.local_sources import shared_files
        app = self.app
        documents = Path(self.directory.name) / 'Documents'
        managed = documents / 'Local' / 'Managed'
        managed.mkdir(parents=True)
        (managed / 'note.txt').write_text('Keep this content')
        use_shared_local(app.private_root, documents)
        provider = shared_files(app.private_root)
        with self.assertRaises(ValueError):
            provider.rename('Local', 'Renamed')
        with self.assertRaises(ValueError):
            delete_resource(provider, 'Local')
        self.assertEqual((managed / 'note.txt').read_text(), 'Keep this content')
        app.loop.run_until_complete(app.show_files())
        self.assertEqual(app.file_provider.root, documents)
        # A recursive search result uses the same editor provider/key as a file
        # opened from a managed workspace or the collection's own browser.
        app.browser_file_selected(provider.entry('Local/Managed/note.txt'))
        with patch.object(app, 'open_crypt', new_callable=AsyncMock) as opened:
            app.loop.run_until_complete(app.read_managed_file())
        self.assertEqual(opened.call_args.kwargs['copies'].provider.root, documents / 'Local')
        self.assertEqual(opened.call_args.kwargs['key'], 'Managed/note.txt')
        app.loop.run_until_complete(app.browser_file_location(('Shared files', 'Local/Managed')))
        self.assertEqual(app.file_provider.root, documents / 'Local')
        self.assertEqual(app.file_path, 'Managed')
        app.pin_local_folder()
        pin = app.pinned_locations().items[0]
        self.assertEqual(pin['path'], 'Managed')
        app.loop.run_until_complete(app.browser_file_location(('Shared files', '')))
        app.loop.run_until_complete(app.pinned_opener(pin)())
        self.assertEqual(app.file_provider.root, documents / 'Local')
        self.assertEqual(app.file_path, 'Managed')

    def test_encrypted_workspace_keeps_one_location_header_without_source_strip(self):
        app = self.app
        app.loop.run_until_complete(app.show_files())
        header = app.file_browser.location_bar
        parent = header.parent
        self.assertIsNone(app.file_source_tabs.parent)
        self.assertIs(parent.children[0], header)
        app.file_changing_location = True
        try:
            app.file_roots['LocalCrypt: Secret'] = 'Secret'
            app.file_storage.items = list(app.file_roots)
            app.file_storage.value = 'LocalCrypt: Secret'
            app.refresh_file_source_tabs()
            app.refresh_file_source_tabs()
            self.assertIsNone(app.file_source_tabs.parent)
            self.assertEqual(app.file_source_buttons, {})
            self.assertIs(parent.children[0], header)
            self.assertEqual(app.file_storage.value, 'LocalCrypt: Secret')
            app.file_storage.value = 'Local files'
            app.refresh_file_source_tabs()
            self.assertIsNone(app.file_source_tabs.parent)
            self.assertIs(parent.children[0], header)
            self.assertIs(header.children[-1], app.file_actions_button)
        finally:
            app.file_changing_location = False

    def test_ios_imported_and_synced_folders_open_directly_above_browse_all(self):
        from mobile_build.tests.transfers.test_mirror_jobs import MirrorClient
        app = self.app
        documents = Path(self.directory.name) / 'Documents'
        (documents / 'Local' / 'Imported').mkdir(parents=True)
        use_shared_local(app.private_root, documents)
        job, _ = app.mirror_store().create(MirrorClient(), 'Drive', 'folder', storage='Local')
        app.show_locations()
        self.assertIn('Imported', app.folder_buttons)
        self.assertIn(job['target'], app.folder_buttons)
        self.assertNotIn('Collection', app.folder_buttons)
        self.assertEqual(list(app.folder_buttons)[-1], 'All files')
        self.assertEqual(app.folder_buttons['All files'].text, 'Browse All Files')
        app.loop.run_until_complete(app.folder_buttons[job['target']].on_press())
        self.assertEqual(app.file_provider.root, documents / 'Local')
        self.assertEqual(app.file_path, job['target'])
        app.show_locations()
        app.loop.run_until_complete(app.folder_buttons['Imported'].on_press())
        self.assertEqual(app.file_path, 'Imported')

    def test_local_shortcut_lists_only_requested_folder_on_cold_and_reused_browser(self):
        from unittest.mock import patch
        from features.rclone.mobile.storage_location import CollectionFiles
        app = self.app
        documents = Path(self.directory.name) / 'Documents'
        folder = documents / 'Local' / 'Server-Lib-Calibre'
        folder.mkdir(parents=True)
        (folder / 'book.epub').write_text('fixture')
        use_shared_local(app.private_root, documents)
        app.show_locations()
        original = CollectionFiles.list
        listed = []
        def listing(provider, path='', **kwargs):
            listed.append(path)
            return original(provider, path, **kwargs)
        for _ in range(2):
            with patch.object(CollectionFiles, 'list', new=listing):
                self.assertTrue(app.loop.run_until_complete(
                    app.browse_hub_folder('Server-Lib-Calibre')))
            self.assertEqual(listed, ['Server-Lib-Calibre'])
            self.assertEqual(app.file_storage.value, 'Local files')
            self.assertEqual(app.file_path, 'Server-Lib-Calibre')
            self.assertEqual({row['name'] for row in app.file_rows.values()}, {'book.epub'})
            app.show_locations()
            listed.clear()

    def test_recycled_browser_keeps_folder_navigation_scroll_contract(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from mobile.folder_navigation import FolderScreen
        app = self.app
        app.loop.run_until_complete(app.show_files())
        browser = app.file_browser
        self.assertIs(browser._scroll, browser)
        native = browser.native_list._impl
        with patch.object(native, 'get_vertical_position', return_value=84, create=True), \
                patch.object(native, 'get_max_vertical_position', return_value=120, create=True), \
                patch.object(native, 'set_vertical_position', create=True) as set_position:
            routes = app.routes
            screen = FolderScreen(app.files_view, browser, app.browser_file_location,
                                  'Local files', '', 'browser')
            routes.folders.screens['files', 'browser'] = screen
            with patch.object(routes, 'screens', {'files': [('browser', app.files_view, None)]}), \
                    patch.object(routes.host, 'state', SimpleNamespace(destination='files')), \
                    patch('mobile.folder_navigation.native_snapshot', Mock(return_value=None)):
                routes.folders.capture()
            self.assertEqual(screen.scroll, 84)
            browser._scroll.vertical_position = min(screen.scroll, browser._scroll.max_vertical_position)
            set_position.assert_called_once_with(84)

    def test_workspace_parent_button_returns_to_hub_after_visiting_child(self):
        app = self.app
        folder = app.private_root / 'LocalFiles' / 'Projects'
        (folder / 'Child').mkdir(parents=True)
        app.show_locations()
        app.loop.run_until_complete(app.browse_hub_folder('Projects'))
        app.loop.run_until_complete(app.browser_file_folder(
            next(row for row in app.file_rows.values() if row['name'] == 'Child')))
        app.loop.run_until_complete(app.parent_file_folder())
        self.assertEqual(app.file_path, 'Projects')
        app.loop.run_until_complete(app.parent_file_folder())
        self.assertFalse(app.routes.screens['files'])
        self.assertEqual(app.native_host.state.destination, 'files')

    def test_mapped_copies_also_appear_locally(self):
        from mobile.folder_hub import source_choices
        choices = {'Offline': dict(source='Local', kind='job', remote='Drive', copies=[
            dict(source='Local', remote='Drive'), dict(source='Remote', remote='Drive')]),
            'Share copy': dict(source='Local', kind='job', remote='Mac', copies=[])}
        self.assertEqual(set(source_choices(choices, 'rclone', {'Mac'})), {'Offline'})
        self.assertEqual(set(source_choices(choices, 'Network shares', {'Mac'})), {'Share copy'})
        self.assertEqual(set(source_choices(choices, 'Local', {'Mac'})), {'Offline', 'Share copy'})

    def test_rows_show_storage_for_selected_tab(self):
        from mobile_build.tests.transfers.test_mirror_jobs import MirrorClient
        class Client(MirrorClient):
            def cancel(self): pass
        app = self.app
        app.cloud_client = Client()
        app.set_loaded_remote_names(['Remote', 'Secret', 'Online'])
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
        self.assertEqual(app.folder_buttons['All files'].text, 'Browse All Files')
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
        from mobile_build.tests.transfers.test_mirror_jobs import MirrorClient
        app = self.app
        class Client(MirrorClient):
            def cancel(self): pass
        app.cloud_client = Client()
        app.set_loaded_remote_names(['Remote', 'Secret'])
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
