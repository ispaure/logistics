"""Mobile masks, physical discovery, session associations and transfer destination safety."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch, AsyncMock
from logisticsmobile.folder_hub import hub_entries, visible_remotes
from logisticsmobile.preferences import Preferences
from features.rclone.mobile.mirror_jobs import MirrorJobs
from test_mirror_jobs import MirrorClient


class FolderHubTests(unittest.TestCase):
    def test_mapped_remote_identity_and_path_wait_off_ui_thread_and_obey_new_navigation(self):
        import asyncio
        from threading import Event, get_ident
        from logisticsmobile.app import LogisticsMobile
        class Client(MirrorClient):
            def crypt_remotes(self): return []
            def cancel(self): pass
        started, release = Event(), Event()
        ui_thread = get_ident()
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            client = app.cloud_client = Client()
            app.show_cloud(present=False)
            app.cloud_remote.items = ['Secret']
            job, _ = app.mirror_store().create(client, 'Secret', 'folder', storage='LocalCrypt')
            app.show_locations()
            entry = next(copy for copy in app.folder_picker_choices[job['target']]['copies'] if copy['source'] == 'Remote')
            identity, request = client.connection_identity, client.request
            def checked_identity(remote):
                self.assertNotEqual(get_ident(), ui_thread)
                started.set()
                if not release.wait(3):
                    raise TimeoutError('Identity check not released')
                return identity(remote)
            def checked_request(action, **values):
                self.assertNotEqual(get_ident(), ui_thread)
                return request(action, **values)
            async def check():
                with patch.object(client, 'connection_identity', side_effect=checked_identity), \
                        patch.object(client, 'request', side_effect=checked_request), \
                        patch.object(app, 'browse_cloud', new=AsyncMock()) as browse:
                    task = asyncio.create_task(app.open_picker_folder(entry))
                    try:
                        for _ in range(100):
                            if started.is_set():
                                break
                            await asyncio.sleep(.01)
                        self.assertTrue(started.is_set())
                        self.assertIn('Checking connection', app.cloud_status.value)
                        app.choose_folder('All files')
                        self.assertFalse(task.done())
                    finally:
                        release.set()
                    self.assertFalse(await task)
                    browse.assert_not_awaited()
                    await app.open_picker_folder(entry)
                    browse.assert_awaited_once_with(preserve_path=True)
                    self.assertEqual(app.cloud_location.value, job['prefix'])
            app.loop.run_until_complete(check())

    def test_return_to_hub_and_options_never_enter_native_discovery(self):
        from logisticsmobile.app import LogisticsMobile
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            app.show_cloud(present=False)
            app.cloud_remote.items = ['First', 'Second']
            app.show_home()
            with patch.object(app, 'existing_crypt_locations', side_effect=AssertionError('Native discovery in UI')) as existing, \
                    patch.object(app, 'linked_crypt_locations', side_effect=AssertionError('Native discovery in UI')) as linked:
                app.show_locations()
                app.choose_folder('Second')
                self.assertEqual(app.folder_picker_selected['remote'], 'Second')
                existing.assert_not_called()
                linked.assert_not_called()

    def test_blocked_discovery_keeps_hub_menu_responsive_and_does_not_steal_navigation(self):
        import asyncio
        from threading import Event, get_ident
        from logisticsmobile.app import LogisticsMobile
        started, release = Event(), Event()
        ui_thread = get_ident()
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            app.show_locations()
            def discover():
                self.assertNotEqual(get_ident(), ui_thread)
                started.set()
                if not release.wait(3):
                    raise TimeoutError('Synthetic discovery was not released')
                return {}
            async def check():
                with patch.object(app, 'existing_crypt_locations', side_effect=discover) as query:
                    task = asyncio.create_task(app.refresh_folder_hub())
                    try:
                        for _ in range(100):
                            if started.is_set():
                                break
                            await asyncio.sleep(.01)
                        self.assertTrue(started.is_set())
                        self.assertIn('Refreshing', app.folder_loading_status.text)
                        app.choose_folder('All files')
                        self.assertEqual(app.routes.screens['files'][-1][0], 'folder-options')
                        self.assertFalse(task.done())
                        self.assertEqual(query.call_count, 1)
                    finally:
                        release.set()
                        await task
                    self.assertEqual(app.routes.screens['files'][-1][0], 'folder-options')
            app.loop.run_until_complete(check())

    def test_busy_online_tap_has_feedback_without_credential_lookup_and_local_stays_available(self):
        from logisticsmobile.app import LogisticsMobile
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            (Path(directory) / 'LocalFiles' / 'Notes').mkdir(parents=True)
            app.show_cloud(present=False)
            app.cloud_remote.items = ['Online']
            app.remote_read_busy = True
            app.set_cloud_busy(True)
            app.show_locations()
            with patch.object(app, 'require_remote_credentials', side_effect=AssertionError('Busy tap must not enter native code')):
                self.assertFalse(app.loop.run_until_complete(app.browse_hub_folder('Online')))
            self.assertIn('connection is busy', app.folder_picker_status.text)
            def controls(widget):
                yield widget
                for child in getattr(widget, 'children', ()):
                    yield from controls(child)
                if getattr(widget, 'content', None) is not None:
                    yield from controls(widget.content)
            self.assertTrue(any(getattr(control, 'text', '') == 'Cancel current request'
                                for control in controls(app.body)))
            self.assertTrue(app.loop.run_until_complete(app.browse_hub_folder('Notes')))
            self.assertEqual(app.file_path, 'Notes')
            self.assertTrue(app.cloud_busy)

    def test_pending_online_folder_does_not_block_a_different_local_folder(self):
        import asyncio
        from logisticsmobile.app import LogisticsMobile
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            (Path(directory) / 'LocalFiles' / 'Notes').mkdir(parents=True)
            app.show_cloud(present=False)
            app.cloud_remote.items = ['Online']
            app.show_locations()
            started, release = asyncio.Event(), asyncio.Event()
            original = app.open_picker_folder
            async def opening(entry):
                if entry['source'] == 'Remote':
                    app.remote_read_busy = True
                    app.set_cloud_busy(True)
                    started.set()
                    await release.wait()
                    app.set_cloud_busy(False)
                    app.remote_read_busy = False
                    return False
                return await original(entry)
            async def check():
                with patch.object(app, 'open_picker_folder', side_effect=opening):
                    pending = asyncio.create_task(app.browse_hub_folder('Online'))
                    try:
                        await started.wait()
                        self.assertTrue(await app.browse_hub_folder('Notes'))
                        self.assertEqual(app.file_path, 'Notes')
                        self.assertFalse(pending.done())
                    finally:
                        release.set()
                        await pending
                    self.assertEqual(app.file_path, 'Notes')
                    self.assertEqual(app.routes.screens['files'][-1][0], 'browser')
            app.loop.run_until_complete(check())

    def test_folder_options_use_displayed_snapshot_without_discovery(self):
        from logisticsmobile.app import LogisticsMobile
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            app.show_locations()
            with patch.object(app, 'folder_choices', side_effect=AssertionError('Menu must not rediscover folders')):
                app.choose_folder('All files')
            self.assertEqual(app.folder_browse_button.text, 'Browse Local')

    def test_folder_tap_shows_loading_rejects_repeat_and_preserves_unlock_page(self):
        import asyncio
        import toga
        from logisticsmobile.app import LogisticsMobile
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            app.show_locations()
            started, release = asyncio.Event(), asyncio.Event()
            unlock_view = toga.Box(children=[toga.Label('Unlock matching credentials')])
            async def open_folder(entry):
                started.set()
                await release.wait()
                app.show_view(unlock_view, destination='files', route='unlock-test', title='Unlock')
                return False
            async def check():
                with patch.object(app, 'open_picker_folder', side_effect=open_folder) as opened:
                    task = asyncio.create_task(app.browse_hub_folder('All files'))
                    await started.wait()
                    self.assertIn('Opening Local folder', app.folder_picker_status.text)
                    self.assertFalse(await app.browse_hub_folder('All files'))
                    self.assertEqual(opened.call_count, 1)
                    release.set()
                    self.assertFalse(await task)
                    self.assertIn(unlock_view, app.body.children)
                    self.assertFalse(app._folder_opening)
            app.loop.run_until_complete(check())

    def test_remote_browsing_does_not_add_contents_to_hub_groups(self):
        from logisticsmobile.app import LogisticsMobile
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                app.show_cloud(present=False)
                app.cloud_remote.items = ['Server-Library-Comics']
                app.cloud_open_remote = 'Server-Library-Comics'
                app.cloud_rows = {'nested': dict(path='folder/inside', directory=True, size=0)}
                local = app.private_root / 'LocalFiles' / 'Local-Comics'
                (local / 'Actual subfolder').mkdir(parents=True)
                app.show_locations()
                self.assertIn('Server-Library-Comics', app.folder_buttons)
                self.assertIn(('Server', 'Library'), app.folder_tree_buttons)
                self.assertNotIn('Local-Comics', app.folder_buttons)
                app.change_folder_source('Local')
                self.assertIn('Local-Comics', app.folder_buttons)
                self.assertFalse(any('/' in name or 'Actual subfolder' in name
                                     for name in app.folder_picker_choices))
            finally:
                app.main_window.close()
                app.loop.close()

    def test_discovery_failure_on_tab_entry_keeps_recovery_page_and_retry_works(self):
        from logisticsmobile.app import LogisticsMobile
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            app.show_locations()
            app.show_home()
            with patch.object(app, 'folder_choices', side_effect=ValueError('Credentials changed')):
                self.assertTrue(app.select_destination('files'))
                root = app.routes.roots['files']
                self.assertTrue(root.children)
                self.assertIn('Credentials changed', app.folder_hub_error)
                recovery = root.children[0]._workspace_frame.main
                self.assertEqual(recovery.children[0].text, 'Folder Hub could not refresh.')
                app.loop.run_until_complete(recovery.children[2].on_press())
                self.assertTrue(app.routes.roots['files'].children)
            app.loop.run_until_complete(app.refresh_folder_hub())
            app.change_folder_source('Local')
            self.assertIn('All files', app.folder_buttons)

    def test_transient_native_credential_index_does_not_clear_folder_rows(self):
        from logisticsmobile.app import LogisticsMobile
        from unittest.mock import PropertyMock
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            app.show_locations()
            with patch.object(type(app.folder_credential), 'value', new_callable=PropertyMock, side_effect=IndexError):
                app.update_folder_list(app.folder_picker_choices)
            app.change_folder_source('Local')
            self.assertIn('All files', app.folder_buttons)
            self.assertTrue(app.folder_list.children)

    def test_dash_hierarchy_keeps_all_levels_and_credential_copies(self):
        from logisticsmobile.folder_hub import folder_tree, credential_choices
        choices = {
            'Server-Lib-ComicRack': dict(remote='Server-Lib-ComicRack', copies=[dict(source='Local')]),
            'Server-Lib-Calibre': dict(remote='Server-Lib-Calibre', copies=[dict(source='Remote')]),
            'Other': dict(remote=None, copies=[])}
        tree = folder_tree(choices)
        self.assertEqual(set(tree['Server']['children']['Lib']['children']), {'ComicRack', 'Calibre'})
        selected = credential_choices(choices, {'Server-Lib-ComicRack'})
        self.assertEqual(list(selected), ['Server-Lib-ComicRack'])
        self.assertIs(selected['Server-Lib-ComicRack'], choices['Server-Lib-ComicRack'])

    def test_list_uses_loaded_remote_values_and_opens_tapped_local_folder(self):
        import toga
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
                view = app.body.children[0]._workspace_frame.main
                self.assertEqual([button.text for button in view.children[0].children], ['rclone', 'Local', 'Network shares'])
                self.assertEqual(view.children[1].children[0].children[0].text, 'Credential')
                self.assertEqual(app.folder_credential.value, 'All')
                self.assertEqual(app.native_host.labels[app.native_host.destinations.index('files')], 'Folder Hub')
                self.assertEqual(view.children[2].children,
                                 [app.folder_transfers_button, app.folder_refresh_button, app.folder_add_share_button])
                self.assertIsInstance(view.children[-1], toga.ScrollContainer)
                self.assertIs(view.children[-1].content, app.folder_list)
                self.assertEqual(set(app.folder_buttons), {'Loaded drive'})
                self.assertFalse(any(isinstance(child, toga.Selection) for child in view.children))
                self.assertIn('↻', app.folder_refresh_button.text)
                self.assertIn('Loaded drive', app.folder_picker_choices)
                app.cloud_remote.items = ['Loaded drive', 'Restored later']
                app.set_cloud_busy(False)
                self.assertIn('Restored later', app.folder_picker_choices)
                self.assertIn('Restored later', app.folder_buttons)
                # Refresh discovers new local folders in the visible list.
                (root.parent / 'Added later').mkdir()
                app.loop.run_until_complete(app.folder_refresh_button.on_press())
                self.assertNotIn('Added later', app.folder_buttons)
                app.change_folder_source('Local')
                self.assertIn('Added later', app.folder_buttons)
                app.change_folder_source('rclone')
                self.assertFalse(app.routes.screens['files'])
                self.assertIn('Comics', app.folder_picker_choices)
                # A newly imported credential is reflected without rebuilding the root.
                app.preferences.save(remote_packages=json.dumps([dict(zip='Loaded.zip',
                    remotes=['Loaded drive'], session_only=True)]))
                app.set_cloud_busy(False)
                self.assertIn('Loaded', app.folder_credentials)
                app.folder_credential.value = 'Loaded'
                self.assertEqual(set(app.folder_buttons), {'Loaded drive'})
                app.folder_credential.value = 'All'
                app.change_folder_source('Local')
                app.loop.run_until_complete(app.folder_buttons['Comics'].on_press())
                self.assertEqual(app.routes.screens['files'][-1][0], 'browser')
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
            def request(self, action, **values):
                if action == 'crypt_path':
                    return dict(path=values.get('path', ''), identity='b' * 64)
                if action == 'crypt_decode':
                    import base64
                    return dict(name='note.md', data=base64.b64encode(b'# Read while pulling').decode())
                return super().request(action, **values)
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
                app.choose_folder('Remote')
                self.assertTrue(app.folder_browse_button.enabled)
                self.assertTrue(all(not button.enabled for button, idle in app.folder_action_controls if idle))
                app.loop.run_until_complete(app.folder_browse_button.on_press())
                self.assertEqual(app.file_path, local['target'])
                cancel = app._crypt_cancel
                app.show_locations()
                app.choose_folder('Secret')
                self.assertTrue(app.folder_browse_button.enabled)
                self.assertTrue(app.loop.run_until_complete(app.open_picker_folder(app.folder_picker_selected)))
                self.assertEqual(app.file_provider.remote, 'Secret')
                row = next(row for row in app.file_rows.values() if not row['directory'])
                app.browser_file_selected(row)
                app.loop.run_until_complete(app.read_managed_file())
                self.assertEqual(app.private_sessions.active.crypt_text.value, '# Read while pulling')
                self.assertTrue(app.cloud_busy and app.transfer_busy)
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

    def test_explicit_browse_actions_follow_existing_copies_and_mapped_scope(self):
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
                app.cloud_remote.items = ['Remote', 'Only online']
                store = app.mirror_store()
                job, _ = store.create(app.cloud_client, 'Remote', 'folder')
                app.show_locations()
                entry = app.folder_picker_choices[job['target']]
                app.show_picker_folder(entry)
                labels = [button.text for button, _ in app.folder_action_controls]
                self.assertEqual([text for text in labels if text.startswith('Browse ')],
                                 ['Browse Local', 'Browse Remote'])
                online = next(copy for copy in entry['copies'] if copy['source'] == 'Remote')
                with patch.object(app, 'browse_cloud', new=AsyncMock()) as browse:
                    app.loop.run_until_complete(app.open_picker_folder(online))
                    self.assertEqual(app.cloud_location.value, 'folder')
                    browse.assert_awaited_once()
                app.show_picker_folder(app.folder_picker_choices['Only online'])
                self.assertEqual([button.text for button, _ in app.folder_action_controls
                                  if button.text.startswith('Browse ')], ['Browse Remote'])
                store.target(job).rename(store.target(job).with_name('Unmapped local'))
                app.show_locations()
                self.assertNotIn(job['target'], app.folder_picker_choices)
                app.show_picker_folder(app.folder_picker_choices['Unmapped local'])
                self.assertEqual([button.text for button, _ in app.folder_action_controls
                                  if button.text.startswith('Browse ')], ['Browse Local'])
                app.show_transfers()
                self.assertEqual(app.transfer_view.content.children[0].text, 'Transfer details')
                self.assertFalse(any(getattr(child, 'text', '') in ('Remote', 'Choose a remote to pull')
                                     for child in app.transfer_view.content.children))
                self.assertNotIn(app.cloud_remote, app.cloud_view.children)
            finally:
                app.main_window.close()
                app.loop.close()

    def test_locked_localcrypt_mapping_keeps_online_action_and_unlock_guard(self):
        from logisticsmobile.app import LogisticsMobile
        class Client(MirrorClient):
            def crypt_remotes(self): return []
            def cancel(self): pass
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            app.cloud_client = Client()
            app.show_cloud(present=False)
            job, _ = app.mirror_store().create(app.cloud_client, 'Secret', 'folder', storage='LocalCrypt')
            app.cloud_remote.items = []
            app.show_locations()
            entry = app.folder_picker_choices[job['target']]
            app.show_picker_folder(entry)
            labels = [button.text for button, _ in app.folder_action_controls]
            self.assertIn('Browse LocalCrypt', labels)
            self.assertIn('Browse Remote', labels)
            self.assertIn('Pull…', labels)
            self.assertIn('Push…', labels)
            self.assertNotIn('Secret', app.loaded_remote_names())
            online = next(copy for copy in entry['copies'] if copy['source'] == 'Remote')
            with patch.object(app, 'require_remote_credentials_async', return_value=False) as require:
                with patch.object(app, 'browse_cloud', new=AsyncMock()) as browse:
                    self.assertFalse(app.loop.run_until_complete(app.open_picker_folder(online)))
                    browse.assert_not_awaited()
                    self.assertEqual(require.call_args.args, ('Secret',))
                    self.assertEqual(require.call_args.kwargs['identity'], job['identity'])
                    resume = require.call_args.kwargs['resume']
            app.cloud_remote.items = ['Secret']
            with patch.object(app, 'require_remote_credentials_async', return_value=True):
                with patch.object(app, 'browse_cloud', new=AsyncMock()) as browse:
                    app.loop.run_until_complete(resume())
                    self.assertEqual(app.cloud_remote.value, 'Secret')
                    self.assertEqual(app.cloud_location.value, job['prefix'])
                    browse.assert_awaited_once_with(preserve_path=True)

    def test_all_three_storage_buttons_and_missing_crypt_copy(self):
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
                app.cloud_remote.items = ['Secret']
                store = app.mirror_store()
                store.create(app.cloud_client, 'Secret', '', storage='Local')
                crypt, _ = store.create(app.cloud_client, 'Secret', '', storage='LocalCrypt')
                def buttons():
                    app.show_locations()
                    app.show_picker_folder(app.folder_picker_choices['Secret'])
                    return [button.text for button, _ in app.folder_action_controls if button.text.startswith('Browse ')]
                self.assertCountEqual(buttons(), ['Browse Local', 'Browse LocalCrypt', 'Browse Remote'])
                store.target(crypt).rename(store.target(crypt).with_name('not-the-mapped-copy'))
                self.assertCountEqual(buttons(), ['Browse Local', 'Browse Remote'])
                app.cloud_remote.items = []
                self.assertCountEqual(buttons(), ['Browse Local', 'Browse Remote'])
            finally:
                app.main_window.close()
                app.loop.close()

    def test_ambiguous_transfer_chooser_routes_to_selected_copy(self):
        from logisticsmobile.app import LogisticsMobile
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                jobs = [dict(id='plain', crypt=False, target='Books'),
                        dict(id='encrypted', crypt=True, target='Books')]
                for push in (False, True):
                    with patch.object(app, 'start_mirror_pull') as pull, patch.object(app, 'start_mirror_review') as review:
                        with patch.object(app, 'show_view') as show:
                            app.choose_transfer_copy(jobs, push=push)
                        view = show.call_args.args[0]
                        view.children[2].on_press()
                        (review if push else pull).assert_called_once_with('encrypted')
                        (pull if push else review).assert_not_called()
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
                              patch.object(store, 'inspect', side_effect=AssertionError('No tree inspection')),
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

    def test_only_existing_crypt_jobs_are_local_and_session_names_do_not_survive_restart(self):
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
            self.assertEqual(json.loads(restored.values['remote_packages']), [])
            self.assertNotIn('credentials.zip', restored.path.read_text())
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
                    from test_mirror_ui import drive_review
                    await app.pull_remote_copy()
                    self.assertEqual(app.routes.screens['files'][-1][0], 'pull-destination')
                    store = app.mirror_store()
                    pull_here = app.body.children[0].children[2].on_press
                    with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=False)):
                        pull_here()
                        self.assertFalse(await drive_review(app, declined=True))
                        self.assertEqual(store.jobs, {})
                    with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)):
                        pull_here()
                        self.assertTrue(await drive_review(app))
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
