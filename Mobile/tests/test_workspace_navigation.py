"""Phone drawers and Duo panes retain the actual document/chat owners."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from logisticsmobile.app import LogisticsMobile


class WorkspaceNavigationTests(unittest.TestCase):
    def test_rotating_a_reader_with_explicit_file_browser_keeps_it_open(self):
        self.app.create_chosen_document('md')
        owner = self.app.editor_view
        owner.editor.value = '# Keep this draft open'
        frame = owner.document_view._workspace_frame
        with patch.object(self.navigation, 'width', return_value=900):
            self.navigation.menu_open['documents'] = True
            self.navigation.render()
            self.assertEqual(len(frame.row.children), 2)
        with patch.object(self.navigation, 'width', return_value=390):
            self.navigation.render()
            self.assertTrue(self.navigation.menu_open['documents'])
            self.assertEqual(len(frame.row.children), 2)
            self.assertTrue(frame.compact_open)
            self.navigation.toggle('documents')
            self.assertFalse(self.navigation.menu_open['documents'])
            self.assertEqual(list(frame.row.children), [frame.main])
        self.assertEqual(owner.editor.value, '# Keep this draft open')

    def test_readers_use_the_same_native_menu_slot_as_documents(self):
        from unittest.mock import PropertyMock
        from Mobile.native_tests.tests.logisticsmobile.fixtures import make_books
        from commonUtils.runtime.document_access import LocalDocuments
        folder = Path(self.directory.name) / 'fixtures'
        folder.mkdir()
        epub, _ = make_books(folder)
        record = self.app.reader_manager().catalog.library_store.import_book(LocalDocuments(), epub)
        self.app.loop.run_until_complete(self.app.open_book(record['id']))
        owner = self.app.readers.active
        menu = owner.library_view._workspace_menu_button
        with patch.object(type(self.app.routes), 'apple', new_callable=PropertyMock, return_value=True):
            self.navigation.prepare(owner.library_view, 'documents', route='reader:test')
            self.assertNotIn(menu, owner.reader_header.children)
            with patch('logisticsmobile.workspace_navigation.mount_native_menu') as mount, patch(
                'logisticsmobile.workspace_navigation.sync_reader_toolbar'
            ) as toolbar:
                self.navigation.render()
                mount.assert_called_once_with(self.app, menu, 'documents')
                toolbar.assert_called_once_with(self.app, owner.library_view, 'documents')

    def test_incoming_workspace_toolbar_uses_destination_before_tab_commit(self):
        app = self.app
        app.show_locations()
        app.select_destination('documents')
        app.native_host.activate('documents')
        self.assertEqual(app.native_host.state.destination, 'documents')
        with patch('logisticsmobile.workspace_navigation.sync_reader_toolbar') as toolbar:
            self.navigation.render(destination='files')
        toolbar.assert_called_once_with(app, app.routes.body('files').children[0], 'files')
        self.assertEqual(app.native_host.state.destination, 'documents')

    def test_toolbar_cleanup_targets_rendered_tab_and_retained_controller(self):
        import sys
        from types import SimpleNamespace as NS
        from unittest.mock import Mock
        from logisticsmobile.workspace_navigation import sync_reader_toolbar
        # Selection callbacks render the incoming tab before state commits.
        reader = Mock(ptr=NS(value=101))
        files = Mock(ptr=NS(value=102))
        files.navigationItem.title = 'Workspaces'
        files.navigationItem.titleView = 'stale comic title'
        files.navigationItem.rightBarButtonItems = ['stale reader actions']
        app = NS(routes=NS(apple=True), native_host=NS(
            state=NS(destination='documents'), destinations=('documents', 'files'),
            adapter=NS(navigation=[NS(topViewController=reader), NS(topViewController=files)])),
            _reader_toolbar_controllers={101, 102}, _reader_toolbar_controller=reader,
            _reader_title_controller=reader, _reader_toolbar_state='retained reader')
        with patch.dict(sys.modules, {'rubicon.objc': NS(ObjCClass=Mock(), CGRect=Mock())}):
            sync_reader_toolbar(app, NS(), 'files')
        self.assertIsNone(files.navigationItem.titleView)
        self.assertIsNone(files.navigationItem.rightBarButtonItems)
        self.assertIsNone(files.navigationItem.prompt)
        self.assertEqual(files.navigationItem.title, 'Workspaces')
        self.assertEqual(app._reader_toolbar_controllers, {101})
        self.assertEqual(app._reader_toolbar_state, 'retained reader')
        self.assertIs(app._reader_toolbar_controller, reader)
        self.assertIs(app._reader_title_controller, reader)

    def setUp(self):
        self.directory = TemporaryDirectory()
        LogisticsMobile.storage_root = Path(self.directory.name)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.app.show_documents(destination='documents')
        self.navigation = self.app.adaptive

    def tearDown(self):
        for drawer in self.navigation.browsers.values():
            if drawer.task is not None and not drawer.task.done():
                drawer.task.cancel()
            self.app.loop.run_until_complete(drawer.browser.close())
        self.app.main_window.close()
        self.app.loop.close()
        LogisticsMobile.storage_root = None
        self.directory.cleanup()

    def test_system_metadata_is_hidden_in_folders_and_file_lists(self):
        from commonUtils.runtime.local_files import LocalFiles
        from logisticsmobile.browser_ui import FileBrowser
        app = self.app
        root = Path(self.directory.name) / 'metadata-fixture'
        root.mkdir()
        for name in ('.DS_Store', 'Thumbs.db', 'THUMBS.DB', 'note.md'):
            (root / name).write_text('fixture')
        browser = FileBrowser(folder_visible=app.folder_path_visible)
        browser.set_entries(LocalFiles(root), '', [
            dict(name=p.name, path=p.name, directory=False, size=p.stat().st_size) for p in root.iterdir()])
        self.assertEqual([row.label for row in browser.entries], ['note.md'])
        for path in ('a/.DS_Store', 'Thumbs.db', 'nested/THUMBS.DB'):
            self.assertFalse(app.folder_path_visible(path, directory=False))
            self.assertFalse(app.folder_path_visible(path))
        app.loop.run_until_complete(browser.close())

    def test_legacy_session_toggle_save_reload_and_platform_scope(self):
        from logisticsmobile.preferences import Preferences
        app = self.app
        backend = type(app._impl)
        with patch.object(backend, '__module__', 'toga_iOS.app'):
            self.assertFalse(app.folder_path_visible('Books/Legacy-old'))
            self.assertFalse(app.folder_path_visible('Legacy-old/book.cbz', directory=False))
            self.assertTrue(app.folder_path_visible('Books/Legacy-file.cbz', directory=False))
            app.show_settings()
            app.settings_navigation.choose('Workspaces')
            app.show_legacy_choice.value = True
            self.assertTrue(app.folder_path_visible('Legacy-old'))
            self.assertEqual(Preferences(app.preferences.path.parent).values['show_legacy'], 'false')
            app.save_preferences()
            self.assertEqual(Preferences(app.preferences.path.parent).values['show_legacy'], 'false')
            app.show_legacy_choice.value = False
            self.assertFalse(app.folder_path_visible('Legacy-old'))
            app.reload_preferences()
            self.assertFalse(app.folder_path_visible('Legacy-old'))
            app.settings_navigation.choose('Workspaces')
            app.show_legacy_choice.value = True
            app.reload_preferences()
            self.assertTrue(app.folder_path_visible('Legacy-old'))
        app.show_legacy_session = False
        self.assertTrue(app.folder_path_visible('Legacy-old'))

    def test_android_legacy_toggle_filters_folders_and_credentials(self):
        from types import SimpleNamespace
        app = self.app
        app.show_settings()
        app.settings_navigation.choose('Workspaces')
        self.assertIsNotNone(app.show_legacy_choice.parent)
        for backend in ('toga_android.app', 'toga_iOS.app'):
            with self.subTest(backend=backend), patch.object(type(app._impl), '__module__', backend):
                app.change_show_legacy(SimpleNamespace(value=False))
                self.assertFalse(app.folder_path_visible('Books/Legacy-old'))
                self.assertFalse(app.legacy_name_visible('LegacyArchive.zip', prefix='legacy'))
                self.assertTrue(app.legacy_name_visible('MyLegacy.zip', prefix='legacy'))
                self.assertTrue(app.folder_path_visible('Books/Legacy-file.cbz', directory=False))
                app.change_show_legacy(SimpleNamespace(value=True))
                self.assertTrue(app.folder_path_visible('Books/Legacy-old'))
                self.assertTrue(app.legacy_name_visible('LegacyArchive.zip', prefix='legacy'))

    def test_legacy_credentials_use_prefix_without_dash_and_toggle_in_place(self):
        import json
        from types import SimpleNamespace
        app = self.app
        packages = [dict(zip=name, remotes=[remote], session_only=True) for name, remote in
                    [('Personal.zip', 'Main'), ('LegacyArchive.zip', 'Old'),
                     ('legacy.zip', 'Old2'), ('MyLegacy.zip', 'Other')]]
        app.show_cloud(present=False)
        for package in packages:
            app.remember_credential_association(package['zip'], package['remotes'], session_only=True)
        app.set_loaded_remote_names(['Main', 'Old', 'Old2', 'Other'])
        app.show_locations()
        with patch.object(type(app._impl), '__module__', 'toga_iOS.app'):
            app.change_show_legacy(SimpleNamespace(value=False))
            self.assertEqual(list(app.folder_credentials), ['All', 'Personal', 'MyLegacy'])
            self.assertEqual([row.value for row in app.folder_credential.items], list(app.folder_credentials))
            app.change_show_legacy(SimpleNamespace(value=True))
            self.assertIn('LegacyArchive', app.folder_credentials)
            app.folder_credential.value = 'LegacyArchive'
            app.change_show_legacy(SimpleNamespace(value=False))
            self.assertEqual(app.folder_credential.value, 'All')
            self.assertEqual(app.folder_credential_name, 'All')
            self.assertEqual(app.session_credential_packages, packages)
            self.assertEqual(json.loads(app.preferences.values['remote_packages']), [])
        self.assertIn('LegacyArchive', app.credential_groups())

    def test_retained_zip_unlock_chooser_skips_legacy_prefix(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        app = self.app
        app.show_cloud(present=False)
        cache = SimpleNamespace(matching=lambda remote, identity: [
            ('old', dict(zip='LegacyArchive.zip')), ('current', dict(zip='Personal.zip'))])
        with patch.object(type(app._impl), '__module__', 'toga_iOS.app'), \
                patch.object(app, 'cloud_client', SimpleNamespace(
                    connection_identity=Mock(side_effect=ValueError('Locked')))), \
                patch.object(app, 'retained_packages', return_value=cache), \
                patch.object(app, 'show_retained_unlock', new_callable=Mock) as unlock:
            app.require_remote_credentials('Main')
            unlock.assert_called_once_with('current', 'Main', identity=None, resume=None)
            app.show_legacy_session = True
            app.require_remote_credentials('Main')
            self.assertEqual(unlock.call_count, 1)
            self.assertEqual(app.routes.screens['files'][-1][0], 'choose-credential')

    def test_browser_filters_folder_paths_and_search_results_for_all_providers(self):
        from types import SimpleNamespace
        from logisticsmobile.browser_ui import FileBrowser
        app = self.app
        with patch.object(type(app._impl), '__module__', 'toga_iOS.app'):
            browser = FileBrowser(selected=lambda row: None, folder_visible=app.folder_path_visible)
            for remote in ('', 'ordinary', 'Legacy-remote'):
                provider = SimpleNamespace(root=Path('/virtual'), relative=lambda path: path, remote=remote)
                rows = [dict(path=path, name=Path(path).name, directory=directory)
                        for path, directory in [('Legacy-old', True), ('Books', True),
                            ('Books/Legacy-file.cbz', False), ('Legacy-old/book.cbz', False)]]
                from commonUtils.runtime.resource_selection import ResourceSelection
                browser.set_entries(ResourceSelection(provider), '', rows)
                expected = [] if remote.startswith('Legacy-') else ['Books', 'Legacy-file.cbz']
                self.assertEqual(sorted(entry.label for entry in browser.entries), expected)
                app.change_show_legacy(SimpleNamespace(value=True))
                browser.query_changed()
                self.assertEqual(len(browser.entries), 4)
                app.change_show_legacy(SimpleNamespace(value=False))
            app.loop.run_until_complete(browser.close())

    def test_private_open_failure_is_visible_in_the_browser(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        app = self.app
        app.show_cloud(present=False)
        drawer = self.navigation.browser('documents')
        drawer.provider = SimpleNamespace(private=True)
        drawer.provider_client = app.cloud_client
        drawer.provider_generation = getattr(app.cloud_client, 'generation', None)
        app.cloud_status.value = 'Private reading failed: fixture archive is damaged'
        with patch.object(app, 'cloud_client', SimpleNamespace(generation=1)):
            drawer.provider_client = app.cloud_client
            drawer.provider_generation = 1
            with patch('features.rclone.localcrypt.mobile.resources.ManagedCopies', return_value=object()),                     patch.object(app, 'open_crypt', new_callable=AsyncMock, return_value=False):
                self.assertFalse(app.loop.run_until_complete(drawer.open_file({'path': 'comic.cbz'})))
        self.assertIn('archive is damaged', drawer.status.text)

    def test_home_title_matches_tab_without_about_command(self):
        import toga
        from types import SimpleNamespace
        from unittest.mock import Mock
        self.assertNotIn(toga.Command.ABOUT, self.app.commands)
        original = self.app.native_host.adapter
        bars = [Mock() for _ in self.app.native_host.destinations]
        self.app.native_host.adapter = SimpleNamespace(navigation=bars)
        try:
            with patch.object(self.navigation, 'render'):
                self.navigation.install()
            self.assertEqual(bars[0].topViewController.navigationItem.title, 'Home')
            bars[0].setNavigationBarHidden.assert_called_once_with(False, animated=False)
            self.assertEqual(self.app.native_host.labels[0], 'Home')
        finally:
            self.app.native_host.adapter = original

    def test_apple_tab_signal_reads_selection_after_native_switch(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from logisticsmobile.navigation import install_apple_selection
        app = self.app
        app.show_home()
        original = app.native_host.adapter
        app.native_host.adapter = SimpleNamespace(navigation=[], controller=SimpleNamespace(view=Mock()))
        try:
            install_apple_selection(app)
            with patch.object(app, 'select_destination', wraps=app.select_destination) as callback:
                app.native_host.on_select = callback
                # UIKit signals the tab item while current_tab still says Home.
                app.native_host.root.on_select()
                self.assertEqual(app.native_host.state.destination, 'home')
                # Its selected controller changes before the queued callback.
                app.native_host.root._impl._set_value('current_tab_index', 2)
                app.native_host.adapter = original
                app.loop.run_until_complete(__import__('asyncio').sleep(0))
                self.assertEqual(app.native_host.state.destination, 'documents')
                self.assertEqual(callback.call_args.args, ('documents',))
        finally:
            app.native_host.adapter = original

    def test_ipad_tab_delegate_keeps_native_and_route_destinations_in_sync(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from logisticsmobile.navigation import install_apple_selection
        app = self.app
        app.native_host.activate('files')
        original = app.native_host.adapter
        controller = SimpleNamespace(view=Mock())
        delegate = SimpleNamespace(owner=None)
        factory = Mock()
        factory.alloc.return_value.init.return_value = delegate
        app.native_host.adapter = SimpleNamespace(navigation=[], controller=controller, sidebar_used=True)
        try:
            with patch('logisticsmobile.navigation.apple_selection_delegate', return_value=factory):
                install_apple_selection(app)
            self.assertIs(controller.delegate, delegate)
            self.assertIs(delegate.owner, app)
            # A modern iPad tab selected Home without the legacy tab-bar event.
            app.native_host.root._impl._set_value('current_tab_index', 0)
            app.native_host.root.on_select()
            app.native_host.root.on_select()  # Coalesce an accompanying legacy notification.
            app.native_host.adapter = original
            app.loop.run_until_complete(__import__('asyncio').sleep(0))
            self.assertEqual(app.native_host.state.destination, 'home')
            self.assertIs(app.body, app.routes.roots['home'])
        finally:
            app.native_host.adapter = original

    def test_queued_first_chat_tap_initializes_and_return_keeps_the_draft(self):
        import asyncio
        from types import SimpleNamespace
        from logisticsmobile.navigation import install_apple_selection
        app = self.app
        app.show_home()
        original = app.native_host.adapter
        app.native_host.adapter = SimpleNamespace(navigation=[])
        install_apple_selection(app)
        app.native_host.adapter = original
        self.assertFalse(hasattr(app, 'chat_view'))
        app.native_host.root.on_select()
        app.native_host.root._impl._set_value('current_tab_index', 3)
        app.loop.run_until_complete(asyncio.sleep(0))
        self.assertEqual(app.native_host.state.destination, 'chat')
        self.assertIn(app.chat_view, app.body.children)
        self.assertIn(app.chat_messages, app.chat_workspace.children)
        app.chat_prompt.value = 'Keep this draft on the next first tap'
        view = app.chat_view
        app.show_home()
        app.native_host.root.on_select()
        app.native_host.root._impl._set_value('current_tab_index', 3)
        app.loop.run_until_complete(asyncio.sleep(0))
        self.assertEqual(app.native_host.state.destination, 'chat')
        self.assertIs(app.chat_view, view)
        self.assertEqual(app.chat_prompt.value, 'Keep this draft on the next first tap')

    def test_menu_opens_without_credential_queries_or_leaving_a_draft(self):
        app = self.app
        app.editor.value = 'Retained while the menu opens'
        frame = app.document_view._workspace_frame
        with patch.object(app, 'existing_crypt_locations', side_effect=AssertionError('No bridge calls in tap')):
            with patch.object(app, 'linked_crypt_locations', side_effect=AssertionError('No bridge calls in tap')):
                with patch.object(app, 'checkpoint', return_value=False):
                    frame.menu.on_press()
                    self.assertTrue(self.navigation.menu_open['documents'])
                    self.assertIn(self.navigation.browser('documents').widget, frame.row.children)
        self.assertEqual(app.editor.value, 'Retained while the menu opens')
        # Preparing the same retained view restores its children; render must
        # rebuild the open drawer even though frame/width/menu state match.
        self.navigation.prepare(app.document_view, 'documents', route='editor')
        self.navigation.render()
        self.assertIn(self.navigation.browser('documents').widget, frame.row.children)
        frame.menu.on_press()
        self.assertFalse(self.navigation.menu_open['documents'])

    def test_connection_query_failure_does_not_break_future_menu_refreshes(self):
        drawer = self.navigation.browser('documents')
        with patch.object(self.app, 'existing_crypt_locations', side_effect=ValueError('Connection locked')):
            self.assertFalse(self.app.loop.run_until_complete(drawer.refresh()))
        self.assertEqual(drawer.status.text, 'Connection locked')
        self.assertTrue(self.app.loop.run_until_complete(drawer.refresh()))

    def test_documents_and_library_paths_read_private_files_during_transfer(self):
        from threading import Event
        from unittest.mock import AsyncMock
        from test_library_catalog import CryptClient
        from features.rclone.localcrypt.mobile.resources import CryptFiles
        app = self.app
        app.show_cloud(present=False)
        client = app.cloud_client = CryptClient()
        client.cancel = lambda: None
        app.cloud_crypt_remotes = {'Remote'}
        provider = CryptFiles(app.private_root / 'LocalCryptFolders', client, 'Remote')
        folder = provider._physical('Collection', directory=True)
        (folder / client.request('crypt_path', path='Comics', directory=True)['path']).mkdir(parents=True)
        (folder / client.request('crypt_path', path='remoteConfig.ini')['path']).write_bytes(
            b'[LogisticsComics]\nlibraries=Comics\n'[::-1])
        logical = 'Collection/Comics/note.md'
        provider._physical(logical).write_bytes(b'# Offline note'[::-1])
        cancel = app.transfer_controller()._transfer_cancel = Event()
        app.cloud_busy = app.transfer_busy = True
        drawer = self.navigation.browser('documents')
        async def exercise():
            self.assertIn('LocalCrypt: Remote', drawer.available_roots())
            self.assertTrue(await drawer.show_main_browser('LocalCrypt: Remote', folder='Collection/Comics'))
            self.assertEqual([row.label for row in drawer.browser.entries], ['note.md'])
            with patch.object(app, 'open_crypt', new=AsyncMock(return_value=True)) as opened:
                self.assertTrue(await drawer.open_file({'path': logical}))
                self.assertTrue(opened.call_args.kwargs['copies'].offline)
                self.assertEqual(opened.call_args.kwargs['key'], logical)
            catalog = app.reader_manager().catalog
            await catalog.refresh_library_folders()
            button = next(button for button in catalog.library_row_buttons if button.text == 'Comics')
            await button.on_press()
            self.assertEqual(app.file_path, 'Collection/Comics')
            self.assertTrue(app.file_provider.private)
            drawer.refresh_menu()
            await next(button for button in drawer.library_buttons if button.text == 'Comics').on_press()
            self.assertEqual(drawer.folder, 'Collection/Comics')
            self.assertTrue(drawer.provider.private)
            self.assertTrue(app.cloud_busy and app.transfer_busy)
            self.assertIs(app.transfer_controller()._transfer_cancel, cancel)
            self.assertFalse(cancel.is_set())
            client.generation += 1
            with patch.object(app, 'open_crypt', new=AsyncMock()) as opened:
                self.assertFalse(await drawer.open_file({'path': logical}))
                opened.assert_not_awaited()
            self.assertIn('Unlock', drawer.status.text)
            app.transfer_busy = False
            self.assertNotIn('LocalCrypt: Remote', drawer.available_roots())
        try:
            app.loop.run_until_complete(exercise())
        finally:
            app.cloud_busy = app.transfer_busy = False
            app.transfer_controller()._transfer_cancel = None

    def test_documents_menu_has_only_comics_and_browse_uses_main_area(self):
        app = self.app
        app.name.value = 'Recent.md'
        app.editor.value = '# Keep this draft'
        key = app.editor_view.session.id
        resource = app.current.id
        app.save_workspace()
        app.close_session(key, choice='keep')
        drawer = self.navigation.browser('documents')
        drawer.refresh_menu()
        labels = [getattr(child, 'text', '') for child in drawer.menu_content.children]
        self.assertIn('Comics Library', labels)
        for label in ('Recent', 'Recent.md', 'Shortcuts', 'Browse Local Files', 'Workspaces', 'New text document'):
            self.assertNotIn(label, labels)
        self.assertTrue(app.open_document(resource))
        self.assertEqual(app.editor.value, '# Keep this draft')
        local = app.private_root / 'LocalFiles'
        local.mkdir(exist_ok=True)
        (local / 'note.md').write_text('# Note')
        (local / 'other.txt').write_text('Other')
        app.loop.run_until_complete(app.open_document_category('Markdown Editor'))
        self.assertEqual(app.routes.screens['documents'][-1][0], 'workspace-browser')
        self.assertEqual([row.label for row in drawer.browser.entries], ['note.md'])
        self.assertFalse(self.navigation.menu_open['documents'])
        self.assertIs(drawer.browser_widget.parent, app.body.children[0]._workspace_frame.main)
        self.assertEqual(app.editor.value, '# Keep this draft')

    def test_folder_actions_pair_tree_at_center_and_collapse_on_phone(self):
        app = self.app
        app.show_locations()
        with patch.object(self.navigation, 'width', return_value=669):
            app.choose_folder('All files')
            frame = app.body.children[0]._workspace_frame
            self.assertEqual(list(frame.row.children), [frame.folder_master, frame.main])
            self.assertLessEqual(abs(frame.folder_master.style.width - frame.main.style.width), 1)
            self.assertEqual(frame.main.style.margin_left, 16)
            self.assertFalse(any(button.text == 'Remove mapping (keep files)'
                                 for button, _ in app.folder_action_controls))
            with patch.object(self.navigation, 'width', return_value=390):
                self.navigation.render()
                self.assertEqual(list(frame.row.children), [frame.main])
                self.assertEqual(frame.main.style.margin_left, 0)
            self.navigation.render()
            self.assertEqual(list(frame.row.children), [frame.folder_master, frame.main])

    def test_workspace_browser_keeps_the_actual_overview_through_rotation_and_back(self):
        app = self.app
        with patch.object(self.navigation, 'width', return_value=900):
            app.show_locations()
            overview = app.body.children[0]._workspace_frame
            controls = app.folder_source_tabs
            self.assertEqual(list(overview.row.children), [overview.main, overview.folder_placeholder])
            app.loop.run_until_complete(app.show_files(local_root=True))
            browser = app.files_view._workspace_frame
            self.assertEqual(list(browser.row.children), [overview.main, browser.main])
            self.assertIs(app.folder_source_tabs, controls)
            with patch.object(self.navigation, 'width', return_value=390):
                self.navigation.render()
                self.assertEqual(list(browser.row.children), [browser.main])
                self.assertEqual(list(overview.row.children), [overview.main])
            self.navigation.render()
            self.assertEqual(list(browser.row.children), [overview.main, browser.main])
            app.routes.back()
            self.assertEqual(list(overview.row.children), [overview.main, overview.folder_placeholder])
            self.assertIs(app.folder_source_tabs, controls)
        app.loop.run_until_complete(app.file_browser.close())

    def test_workspace_hinge_reflows_without_a_window_resize(self):
        app = self.app
        with patch.object(self.navigation, 'width', return_value=900):
            app.show_locations()
            app.loop.run_until_complete(app.show_files(local_root=True))
            frame = app.files_view._workspace_frame
            with patch('logisticsmobile.fold_layout.seam_fraction', return_value=.54):
                self.navigation.render()
                available = self.navigation.content_width('files', margin=24)
                self.assertAlmostEqual(frame.folder_master.style.width + 8, available * .54, delta=1)
                self.assertAlmostEqual(frame.main.style.width + 8, available * .46, delta=1)
                self.assertEqual(frame.main.style.margin_left, 16)
            self.navigation.render()
            self.assertAlmostEqual(frame.folder_master.style.width, frame.main.style.width)
        app.loop.run_until_complete(app.file_browser.close())

    def test_workspace_uses_allocated_width_after_the_tablet_rail(self):
        app = self.app
        app.show_locations()
        with patch.object(self.navigation, 'width', return_value=700), patch.object(
                self.navigation, 'content_width', return_value=600):
            app.choose_folder('All files')
            frame = app.body.children[0]._workspace_frame
            self.assertEqual(list(frame.row.children), [frame.main])

    def test_remote_and_scoped_browsers_share_the_retained_workspace_list(self):
        import toga
        from toga.style import Pack
        app = self.app
        app.show_locations()
        overview = app.body.children[0]._workspace_frame
        controls = app.folder_source_tabs
        with patch.object(self.navigation, 'width', return_value=900):
            for route in ('remote-browser', 'workspace-browser', 'folder-options'):
                view = toga.Box(style=Pack(flex=1))
                app.show_view(view, destination='files', route=route)
                frame = view._workspace_frame
                self.assertEqual(list(frame.row.children), [overview.main, frame.main])
                self.assertIs(app.folder_source_tabs, controls)
                app.change_folder_source('rclone')
                self.assertIs(app.folder_source_tabs, controls)
                app.routes.back()
                self.assertEqual(list(overview.row.children), [overview.main, overview.folder_placeholder])

    def test_phone_file_drawer_opens_a_nested_file_without_losing_editor_draft(self):
        app = self.app
        app.editor.value = 'Keep the original draft'
        first = app.editor_view
        with patch.object(self.navigation, 'width', return_value=390):
            first.document_view._workspace_frame.menu.on_press()
            drawer = self.navigation.browser('documents')
            (app.private_root / 'LocalFiles' / 'Notes').mkdir(parents=True, exist_ok=True)
            (app.private_root / 'LocalFiles' / 'Notes' / 'Another.md').write_text('# Other file')
            app.loop.run_until_complete(drawer.task)
            frame = first.document_view._workspace_frame
            self.assertEqual(list(frame.row.children), [drawer.widget, frame.main])
            app.loop.run_until_complete(drawer.open_folder({'path': 'Notes'}))
            entry = next(item for item in drawer.browser.entries if item.label == 'Another.md')
            app.loop.run_until_complete(drawer.browser.activate_entry(entry))
            self.assertEqual(app.native_host.state.destination, 'documents')
            self.assertFalse(self.navigation.menu_open['documents'])
            self.assertEqual(first.document.text, 'Keep the original draft')
            self.assertEqual(app.private_sessions.active.crypt_text.value, '# Other file')
            opened = app.private_sessions.active.session.id
            self.assertTrue(app.routes.back())
            self.assertNotIn(opened, app.workspace.sessions)
            self.assertIn(first.session.id, app.workspace.sessions)
            self.assertEqual(first.document.text, 'Keep the original draft')
            self.assertIs(app.body.children[0], first.document_view)
            self.assertTrue(self.navigation.menu_open['documents'])
            self.assertEqual(drawer.folder, 'Notes')

    def test_duo_switches_browser_and_two_editors_and_collapses_without_copying_widgets(self):
        app = self.app
        first = app.editor_view
        first.editor.value = 'A draft'
        app.new_document()
        second = app.editor_view
        second.editor.value = 'B draft'
        self.navigation.pinned = first.session.id
        with patch.object(self.navigation, 'width', return_value=1100):
            self.navigation.render()
            frame = second.document_view._workspace_frame
            self.assertEqual(list(frame.row.children), [first.document_view._workspace_frame.main, frame.main])
            self.assertEqual(self.navigation.diagnostics()['layout'], 'two-documents')
            frame.menu.on_press()
            drawer = self.navigation.browser('documents')
            self.assertEqual(list(frame.row.children), [drawer.widget, frame.main])
            frame.menu.on_press()
            self.assertEqual(list(frame.row.children), [first.document_view._workspace_frame.main, frame.main])
            first.editor.value = 'Edited on left'
            self.assertEqual(second.document.text, 'B draft')
            self.assertEqual(app.store.open(first.document.id).text, 'Edited on left')
        # The wider Duo portrait display is narrower than a regular iPad.
        with patch.object(self.navigation, 'width', return_value=669):
            self.navigation.render()
            self.assertEqual(self.navigation.diagnostics()['layout'], 'two-documents')
            self.assertEqual(list(frame.row.children), [first.document_view._workspace_frame.main, frame.main])
        with patch.object(self.navigation, 'width', return_value=390):
            self.navigation.render()
            self.assertEqual(list(frame.row.children), [frame.main])
            self.assertEqual(first.document.text, 'Edited on left')
        app.close_session(first.session.id)
        self.assertIsNone(self.navigation.pinned)
        self.assertEqual(second.document.text, 'B draft')

    def test_files_drawer_retains_current_folder_and_native_back_route(self):
        app = self.app
        app.show_cloud(present=False)
        with patch.object(self.navigation, 'width', return_value=390):
            app.loop.run_until_complete(app.show_files())
            frame = app.files_view._workspace_frame
            original = app.file_browser
            frame.menu.on_press()
            self.assertEqual(list(frame.row.children), [self.navigation.browser('files').widget, frame.main])
            frame.menu.on_press()
            self.assertEqual(list(frame.row.children), [frame.main])
            self.assertIs(app.file_browser, original)
            self.assertTrue(app.routes.back())
            self.assertEqual(app.native_host.state.destination, 'files')

    def test_overview_drawer_keeps_overview_and_editor_draft(self):
        app = self.app
        owner = app.editor_view
        owner.editor.value = 'Draft before opening the overview'
        app.show_documents_hub()
        overview = app.body.children[0]
        frame = overview._workspace_frame
        with patch.object(self.navigation, 'width', return_value=390):
            frame.menu.on_press()
            self.assertIs(app.body.children[0], overview)
            self.assertEqual(list(frame.row.children),
                             [self.navigation.browser('documents').widget, frame.main])
            self.assertLess(self.navigation.browser('documents').widget.style.width, 390)
            self.assertTrue(frame.compact_open)
            frame.menu.on_press()
            self.assertEqual(list(frame.row.children), [frame.main])
            self.assertEqual(owner.editor.value, 'Draft before opening the overview')

    def test_files_hamburger_works_on_first_tab_selection_without_refresh(self):
        app = self.app
        app.show_home()
        with patch.object(self.navigation, 'width', return_value=390):
            # Match native selection ordering: the callback precedes state.select.
            self.assertTrue(app.select_destination('files'))
            app.native_host.state.select('files')
            frame = app.routes.body('files').children[0]._workspace_frame
            self.assertEqual(self.navigation.last_layout[0], id(frame))
            frame.menu.on_press()
            drawer = self.navigation.browser('files')
            app.loop.run_until_complete(drawer.task)
            self.assertTrue(self.navigation.menu_open['files'])
            self.assertIsNotNone(drawer.provider)
            self.assertEqual(list(frame.row.children), [drawer.widget, frame.main])
            self.assertEqual(len(app.routes.screens['files']), 0)
            frame.menu.on_press()
            self.assertEqual(list(frame.row.children), [frame.main])

    def test_split_picker_can_open_a_retained_session_without_an_existing_editor(self):
        app = self.app
        first = app.editor_view
        stored = app.store.create('Retained second.txt')
        second = app.workspace.open('managed-text', stored.id, 'text', stored.name)
        app.workspace.activate(first.session.id)
        self.assertNotIn(second.id, app.text_views)
        with patch.object(self.navigation, 'width', return_value=669):
            first.document_view._workspace_frame.pair.on_press()
            content = app.body.children[0].content
            next(button for button in content.children if getattr(button, 'text', '') == stored.name).on_press()
            self.assertEqual(app.workspace.active, second.id)
            self.assertEqual(self.navigation.pinned, first.session.id)
            self.assertIn(second.id, app.text_views)
            self.assertEqual(self.navigation.diagnostics()['layout'], 'two-documents')

    def test_chat_conversation_drawer_is_full_height_on_phone_and_half_on_duo(self):
        app = self.app
        with patch.object(self.navigation, 'width', return_value=390):
            app.show_chat()
            first = app.chat_current['id']
            app.chat_prompt.value = 'Unsent first conversation'
            app.new_chat()
            second = app.chat_current['id']
            app.chat_prompt.value = 'Unsent second conversation'
            app.toggle_chat_conversations()
            self.assertEqual(list(app.chat_workspace.children), [app.chat_sidebar])
            app.open_chat(first)
            self.assertEqual(app.chat_prompt.value, 'Unsent first conversation')
            self.assertEqual(list(app.chat_workspace.children), [app.chat_messages])
            self.assertEqual(app.chat_store.load(second)['draft'], 'Unsent second conversation')
        with patch.object(self.navigation, 'width', return_value=1100):
            app.toggle_chat_conversations()
            self.assertEqual(list(app.chat_workspace.children), [app.chat_sidebar, app.chat_messages])
            app.show_chat_configuration()
            self.assertIs(app.body.children[0], app.chat_config_view)
            self.assertTrue(app.routes.back())
            self.assertIs(app.body.children[0], app.chat_view)
        app.show_settings()
        self.assertEqual(app.native_host.state.destination, 'settings')
        self.assertIs(app.body, app.routes.roots['settings'])
