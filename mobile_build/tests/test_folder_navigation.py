"""Folder Back stacks and explicit reader-to-folder navigation."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import toga
from commonUtils.ui.native.navigation import NativeNavigationHost
from mobile.app import LogisticsMobile
from mobile.folder_navigation import record
from mobile.navigation import DESTINATION_ITEMS
from mobile.routes import MobileRoutes
from mobile_build.tests.test_native_reader_return import Navigation


class FolderStackTests(TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.addCleanup(self.loop.close)
        self.host = NativeNavigationHost(DESTINATION_ITEMS)
        self.app = SimpleNamespace(loop=self.loop, native_host=self.host, active_host=True,
            select_destination=Mock(return_value=True), visible_reader=Mock(return_value=None),
            reader_tool_back=Mock(return_value=None),
            adaptive=SimpleNamespace(render=Mock()))
        self.routes = self.app.routes = MobileRoutes(self.app, self.host, guard=lambda: True, changed=Mock())
        self.navigation = [Navigation() for _ in self.host.destinations]
        def push(destination, panel, title):
            controller = SimpleNamespace(title=title)
            self.navigation[self.host.destinations.index(destination)].viewControllers.append(controller)
            return SimpleNamespace(controller=controller)
        self.host.adapter = SimpleNamespace(navigation=self.navigation, push=push,
            containers=[(None, nav.viewControllers[0]) for nav in self.navigation], release_pane=Mock())
        self.view = toga.Box()
        self.header = toga.Box(children=[toga.Button('Up')])
        self.header.parent_button = self.header.children[0]
        self.browser = SimpleNamespace(location_bar=self.header, search=SimpleNamespace(value=''),
            selected=None, entries=[])
        self.loaded = []
        async def navigate(location):
            self.loaded.append(location)
            record(self.app, self.view, self.browser, 'browser', *location, navigate)
            return True
        self.navigate = navigate
        self.routes.show(toga.Label('Workspaces'), destination='files', root=True)

    def show(self, path):
        record(self.app, self.view, self.browser, 'browser', 'Local files', path, self.navigate)
        self.routes.show(self.view, destination='files', route='browser')

    def finish(self):
        self.loop.run_until_complete(self.routes.folders.task)

    def test_direct_entry_builds_ancestors_and_native_pop_loads_parent(self):
        self.show('Projects/Reports')
        self.assertEqual([screen[2].controller.title for screen in self.routes.screens['files']],
                         ['Local files', 'Projects', 'Reports'])
        self.assertTrue(all(panel.children for _, panel, _ in self.routes.screens['files']))
        self.assertNotIn(self.header.parent_button, self.header.children)
        nav = self.navigation[self.host.destinations.index('files')]
        nav.viewControllers.pop()
        self.routes.native_popped(nav)
        self.finish()
        self.assertEqual(self.loaded, [('Local files', 'Projects')])
        self.assertIs(self.routes.body().children[0], self.view)
        self.routes.back()
        with patch('mobile.folder_title.mount') as mount:
            self.finish()
            self.assertIs(mount.call_args.args[0], self.header)
            self.assertEqual(mount.call_args.args[2], 'Local files')
        self.assertEqual(self.loaded[-1], ('Local files', ''))
        self.routes.back()
        self.assertFalse(self.routes.screens['files'])
        self.assertEqual(self.host.state.destination, 'files')

    def test_home_picker_ancestors_keep_the_opening_reader_below_their_scope(self):
        self.host.activate('home')
        reader = toga.Label('Retained Home reader')
        self.routes.show(reader, route='reader:origin')
        self.view._folder_return_count = 1
        self.view._folder_scope = 'picker-one'
        record(self.app, self.view, self.browser, 'workspace-browser', 'Local files',
               'Projects/Reports', self.navigate)
        self.routes.show(self.view, destination='home', route='workspace-browser')
        self.assertEqual(len(self.routes.screens['home']), 4)
        self.assertIs(self.routes.screens['home'][0][1].children[0], reader)
        nav = self.navigation[self.host.destinations.index('home')]
        self.assertEqual([screen[2].controller.title for screen in self.routes.screens['home'][1:]],
                         ['Local files', 'Projects', 'Reports'])
        nav.viewControllers = nav.viewControllers[:2]
        self.routes.native_popped(nav)
        self.assertIs(self.routes.body().children[0], reader)
        self.assertFalse(self.routes.origins)

    def test_workspace_shortcut_back_returns_to_overview_without_storage_ancestors(self):
        self.view._folder_entry_location = ('Local files', 'Projects/Reports')
        self.show('Projects/Reports')
        self.assertEqual([screen[2].controller.title for screen in self.routes.screens['files']], ['Reports'])
        self.show('Projects/Reports/Invoices')
        self.assertEqual([screen[2].controller.title for screen in self.routes.screens['files']],
                         ['Reports', 'Invoices'])
        self.routes.back()
        self.finish()
        self.assertEqual(self.loaded[-1], ('Local files', 'Projects/Reports'))
        self.routes.back()
        self.assertFalse(self.routes.screens['files'])
        self.assertEqual(self.routes.body().children[0].text, 'Workspaces')

    def test_workspace_shortcut_native_pop_returns_directly_to_overview(self):
        self.view._folder_entry_location = ('Local files', 'Projects')
        self.show('Projects')
        nav = self.navigation[self.host.destinations.index('files')]
        nav.viewControllers.pop()
        self.routes.native_popped(nav)
        self.assertFalse(self.routes.screens['files'])
        self.assertFalse(self.loaded)
        self.assertEqual(self.routes.body().children[0].text, 'Workspaces')

    def test_parent_query_is_restored_and_failed_parent_remains_navigable(self):
        self.show('Projects')
        self.browser.search.value = 'report'
        self.routes.folders.capture()
        self.show('Projects/Reports')
        self.routes.back()
        self.finish()
        self.assertEqual(self.browser.search.value, 'report')
        async def fail(location):
            return False
        root = self.routes.folders.screens['files', self.routes.screens['files'][0][0]]
        root.navigate = fail
        self.routes.back()
        self.finish()
        self.assertIn('Could not open folder', self.routes.body().children[0].text)
        self.routes.back()
        self.assertFalse(self.routes.screens['files'])

    def test_parent_load_finishes_in_retained_workspace_after_switching_tabs(self):
        self.show('Projects/Reports')
        self.routes.back()
        self.host.activate('home')
        self.finish()
        self.assertEqual(self.host.state.destination, 'home')
        self.assertIs(self.routes.body('files').children[0], self.view)
        self.assertEqual(self.loaded, [('Local files', 'Projects')])

    def test_reader_back_retains_folder_without_listing_and_guard_refusal_keeps_stack(self):
        self.show('Projects/Reports')
        self.routes.show(toga.Label('Reader'), route='private:file')
        self.routes.back()
        self.assertFalse(self.loaded)
        self.assertIs(self.routes.body().children[0], self.view)
        self.routes.guard = lambda: False
        self.routes.back()
        self.assertEqual(len(self.routes.screens['files']), 3)

    def test_native_reader_return_restores_viewport_after_final_native_reflow(self):
        self.show('Projects/Reports')
        scroll = self.browser._scroll = SimpleNamespace(vertical_position=120, max_vertical_position=1000)
        self.routes.show(toga.Label('Reader'), route='private:file')
        scroll.vertical_position = 164
        def shifted_layout():
            scroll.vertical_position += 44
        self.app.adaptive.render.side_effect = shifted_layout
        nav = self.navigation[self.host.destinations.index('files')]
        nav.viewControllers.pop()
        self.routes.native_popped(nav)
        self.loop.run_until_complete(asyncio.sleep(0))
        self.assertEqual(scroll.vertical_position, 120)
        self.assertFalse(self.loaded)
        self.assertIs(self.routes.body().children[0], self.view)

    def test_loading_replacement_preserves_original_viewport_through_explicit_back(self):
        self.show('Projects/Reports')
        scroll = self.browser._scroll = SimpleNamespace(vertical_position=120, max_vertical_position=1000)
        self.routes.show(toga.Label('Opening'), route='file-loading:fixture')
        scroll.vertical_position = 76
        self.routes.show(toga.Label('Reader'), route='private:file')
        nav = self.navigation[self.host.destinations.index('files')]
        original = nav.popToViewController
        def pop(controller, animated):
            original(controller, animated=animated)
            self.routes.native_popped(nav)
        nav.popToViewController = pop
        def shifted_layout():
            scroll.vertical_position -= 44
        self.app.adaptive.render.side_effect = shifted_layout
        self.routes.back()
        self.loop.run_until_complete(asyncio.sleep(0))
        self.assertEqual(scroll.vertical_position, 120)
        self.assertFalse(self.loaded)
        self.assertIs(self.routes.body().children[0], self.view)

    def test_queued_reader_restore_does_not_reset_a_new_folder_viewport(self):
        self.show('Projects/Reports')
        scroll = self.browser._scroll = SimpleNamespace(vertical_position=120, max_vertical_position=1000)
        self.routes.show(toga.Label('Reader'), route='private:file')
        nav = self.navigation[self.host.destinations.index('files')]
        nav.viewControllers.pop()
        self.routes.native_popped(nav)
        self.show('Other')
        scroll.vertical_position = 300
        self.loop.run_until_complete(asyncio.sleep(0))
        self.assertEqual(scroll.vertical_position, 300)

    def test_multi_level_native_pop_and_other_tab_reader_are_independent(self):
        reader = toga.Label('Home reader')
        self.host.activate('home')
        self.routes.show(reader, destination='home', route='reader:file')
        self.show('A/B/C')
        nav = self.navigation[self.host.destinations.index('files')]
        nav.viewControllers = nav.viewControllers[:2]
        self.routes.native_popped(nav)
        self.finish()
        self.assertEqual(self.loaded, [('Local files', '')])
        self.assertIs(self.routes.body('home').children[0], reader)
        self.assertFalse(self.routes.origins)


class ShowInFolderTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        LogisticsMobile.storage_root = Path(directory.name)
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(self.app.loop.close)
        self.addCleanup(self.app.main_window.close)
        self.app.show_cloud(present=False)
        self.folder = self.app.private_root / 'LocalFiles' / 'Projects' / 'Reports'
        self.folder.mkdir(parents=True)
        self.path = self.folder / 'note.txt'
        self.path.write_text('Keep my draft')

    def test_parent_list_is_mounted_before_pop_while_refresh_is_blocked(self):
        from mobile.browser_ui import FileBrowser
        from features.rclone.mobile.storage_location import CollectionFiles
        app = self.app
        host = NativeNavigationHost(DESTINATION_ITEMS)
        owner = SimpleNamespace(loop=app.loop, native_host=host, active_host=True,
            folder_path_visible=app.folder_path_visible, adaptive=SimpleNamespace(wide=False),
            select_destination=Mock(return_value=True), visible_reader=Mock(return_value=None),
            reader_tool_back=Mock(return_value=None))
        routes = owner.routes = MobileRoutes(owner, host, guard=lambda: True, changed=Mock())
        navigation = [Navigation() for _ in host.destinations]
        def push(destination, panel, title):
            controller = SimpleNamespace(title=title)
            navigation[host.destinations.index(destination)].viewControllers.append(controller)
            return SimpleNamespace(controller=controller)
        host.adapter = SimpleNamespace(navigation=navigation, push=push,
            containers=[(None, nav.viewControllers[0]) for nav in navigation], release_pane=Mock())
        provider = CollectionFiles(app.private_root)
        browser = FileBrowser()
        view = toga.Box(children=[browser.scroll_container()])
        view._folder_entry_location = ('Local files', 'Projects')
        release = asyncio.Event()
        async def navigate(location):
            await release.wait()
            browser.set_entries(provider, location[1], provider.list(location[1]))
            return True
        async def exercise():
            routes.show(toga.Label('Workspaces'), destination='files', root=True)
            browser.set_entries(provider, 'Projects', provider.list('Projects'))
            record(owner, view, browser, 'browser', 'Local files', 'Projects', navigate)
            routes.show(view, destination='files', route='browser')
            routes.folders.capture()
            parent = routes.screens['files'][0][1]
            entry = routes.folders.screens['files', routes.screens['files'][0][0]]
            preview = entry.preview
            self.assertIsNone(preview.task)
            browser.set_entries(provider, 'Projects/Reports', provider.list('Projects/Reports'))
            record(owner, view, browser, 'browser', 'Local files', 'Projects/Reports', navigate)
            self.assertIs(parent.children[0], preview.view)
            self.assertEqual([item.label for item in preview.browser.entries], ['Reports'])
            routes.back()
            await asyncio.sleep(0)
            self.assertFalse(routes.folders.task.done())
            self.assertIs(routes.body().children[0], preview.view)
            self.assertEqual([item.label for item in preview.browser.entries], ['Reports'])
            release.set()
            await routes.folders.task
            self.assertIs(routes.body().children[0], view)
            routes.trim('files', 0)
            await browser.close()
            await asyncio.sleep(0)
        app.loop.run_until_complete(exercise())

    def test_home_file_action_opens_local_browser_while_cloud_restore_is_blocked(self):
        app = self.app
        async def exercise():
            app.show_home()
            release = asyncio.Event()
            async def restore():
                await release.wait()
            app.cloud_restore_task = app.loop.create_task(restore())
            try:
                self.assertTrue(await asyncio.wait_for(app.open_hub_file(), 1))
                self.assertFalse(app.cloud_restore_task.done())
                self.assertEqual(app.native_host.state.destination, 'home')
                self.assertEqual(app.adaptive.browser('home').storage.value, 'Local files')
            finally:
                release.set()
                await app.cloud_restore_task
        app.loop.run_until_complete(exercise())

    def test_home_picker_cancel_returns_to_its_origin_and_reopening_has_separate_controls(self):
        app = self.app
        async def exercise():
            app.show_home()
            origin = app.body
            await app.open_hub_file()
            first = app.adaptive.browser('home')
            self.assertIn(first.cancel_button, first.browser.location_bar.children)
            self.assertNotIn(first.workspaces_button, first.browser_widget.children)
            await first.open_folder({'path': 'Projects'})
            await first.open_file({'path': 'Projects/Reports/note.txt'})
            reader = app.body
            await app.open_hub_file()
            second = app.adaptive.browser('home')
            self.assertIsNot(first, second)
            second.cancel_browser()
            self.assertIs(app.body, reader)
            app.routes.back()
            self.assertIs(app.body.children[0], first.page)
            first.cancel_browser()
            self.assertIs(app.body, origin)
            await first.browser.close()
            await second.browser.close()
        app.loop.run_until_complete(exercise())

    def test_home_import_reveals_file_in_workspaces_and_keeps_reader(self):
        from mobile.document_sources import folder_action, show_in_folder
        app = self.app
        async def exercise():
            app.show_home()
            self.assertTrue(await app.open_download(path=self.path))
            reader = app.body
            session = app.workspace.sessions[app.workspace.active]
            self.assertEqual(folder_action(app, session)[0][0], 'Show in folder')
            self.assertTrue(await show_in_folder(app, session))
            self.assertEqual(app.native_host.state.destination, 'files')
            self.assertEqual(app.file_path, 'Projects/Reports')
            selected = next(item for item in app.file_browser.entries if item.identity == app.file_browser.selected)
            self.assertEqual(selected.payload['name'], 'note.txt')
            self.assertIs(app.routes.body('home'), reader)
            self.assertFalse(app.routes.origins)
        app.loop.run_until_complete(exercise())

    def test_native_folder_header_has_one_title_and_keeps_storage_identity_and_actions(self):
        from mobile.browser_ui import FolderLocationHeader
        app = self.app
        async def exercise():
            await app.show_files()
            header = app.file_browser.location_bar
            self.assertIsInstance(header, FolderLocationHeader)
            header.use_native_title()
            header.update('Projects/Reports')
            self.assertNotIn(header.folder_name, header.caption.children)
            self.assertEqual(header.folder_name.value, 'Reports')
            self.assertIn(header.storage_identity, header.caption.children)
            self.assertIn(app.file_browser.search_button, header.title_actions)
            self.assertIn(app.file_actions_button, header.title_actions)
            self.assertNotIn(header.native_actions, header.children)
        app.loop.run_until_complete(exercise())

    def test_direct_ancestor_preview_lists_parent_before_back(self):
        from mobile.folder_navigation import FolderPreview, FolderScreen
        app = self.app
        async def exercise():
            await app.show_files()
            await app.browser_file_location(('Local files', 'Projects/Reports'))
            entry = FolderScreen(app.files_view, app.file_browser, app.browser_file_location,
                                 'Local files', 'Projects', 'browser')
            preview = FolderPreview(app, entry)
            try:
                self.assertTrue(preview.view.children)
                await preview.task
                self.assertEqual([item.label for item in preview.browser.entries], ['Reports'])
                self.assertEqual(app.file_path, 'Projects/Reports')
            finally:
                preview.close()
                await preview.browser.close()
        app.loop.run_until_complete(exercise())

    def test_markdown_preview_offers_the_same_folder_action(self):
        app = self.app
        path = self.folder / 'note.md'
        path.write_text('# Source document')
        async def exercise():
            app.show_home()
            self.assertTrue(await app.open_download(path=path))
            app.show_preview()
            self.assertIn('Show in folder', [label for label, _ in app.editor_view.preview_actions.actions])
        app.loop.run_until_complete(exercise())

    def test_encrypted_reader_reveals_scoped_folder_and_preserves_session(self):
        from features.rclone.localcrypt.mobile.resources import CryptFiles, ManagedCopies
        from mobile_build.tests.test_storage_reader_opening import ReaderClient
        from mobile.document_sources import show_in_folder
        app = self.app
        app.cloud_client = client = ReaderClient()
        provider = CryptFiles(app.private_root / 'LocalCryptFolders', client, 'Secret')
        provider._physical('note.txt').write_bytes(b'encrypted draft'[::-1])
        async def exercise():
            app.show_home()
            self.assertTrue(await app.open_crypt(copies=ManagedCopies(provider), key='note.txt'))
            owner = app.private_sessions.active
            self.assertIn('Show in folder', [label for label, _ in owner.crypt_actions_menu.actions])
            self.assertTrue(await show_in_folder(app, owner.session))
            drawer = app.adaptive.browser('files')
            self.assertIs(drawer.provider, provider)
            self.assertEqual(app.native_host.state.destination, 'files')
            self.assertIn(owner.session.id, app.workspace.sessions)
            await drawer.browser.close()
        app.loop.run_until_complete(exercise())

    def test_remote_reader_reveals_original_remote_and_selects_file(self):
        from features.rclone.mobile.remote_readers import RemoteReaders
        from mobile_build.tests.test_remote_readers import RemoteClient
        from mobile.document_sources import show_in_folder, folder_action
        app = self.app
        app.cloud_client = client = RemoteClient()
        app.set_loaded_remote_names(['Files'])
        async def exercise():
            app.show_home()
            self.assertTrue(await app.open_crypt(copies=RemoteReaders(client, 'Files'), key='note.txt'))
            owner = app.private_sessions.active
            reader = app.body
            self.assertTrue(await show_in_folder(app, owner.session))
            self.assertEqual(app.cloud_open_remote, 'Files')
            self.assertEqual(app.native_host.state.destination, 'files')
            selected = next(item for item in app.remote_browser.entries if item.identity == app.remote_browser.selected)
            self.assertEqual(selected.payload['path'], 'note.txt')
            self.assertIs(app.routes.body('home'), reader)
            client.generation += 1
            self.assertFalse(folder_action(app, owner.session))
        app.loop.run_until_complete(exercise())

    def test_provider_text_reveals_original_and_unbacked_document_has_no_action(self):
        from commonUtils.runtime.local_files import LocalFiles
        from features.text_editor.resources import LocalTextCopies
        from mobile.document_sources import folder_action, show_in_folder
        app = self.app
        async def exercise():
            app.show_home()
            self.assertTrue(await app.open_crypt(copies=LocalTextCopies(LocalFiles(self.folder)), key='note.txt'))
            owner = app.private_sessions.active
            owner.crypt_text.value = 'Unsaved provider draft'
            self.assertIn('Show in folder', [label for label, _ in owner.crypt_actions_menu.actions])
            self.assertTrue(await show_in_folder(app, owner.session))
            self.assertEqual(app.file_path, 'Projects/Reports')
            self.assertEqual(owner.crypt_text.value, 'Unsaved provider draft')
            app.create_chosen_document('txt')
            self.assertFalse(folder_action(app, app.editor_view.session))
        app.loop.run_until_complete(exercise())
