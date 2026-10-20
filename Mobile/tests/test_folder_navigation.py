"""Folder Back stacks and explicit reader-to-folder navigation."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

import toga
from commonUtils.ui.native.navigation import NativeNavigationHost
from logisticsmobile.app import LogisticsMobile
from logisticsmobile.folder_navigation import record
from logisticsmobile.navigation import DESTINATION_ITEMS
from logisticsmobile.routes import MobileRoutes
from Mobile.tests.test_native_reader_return import Navigation


class FolderStackTests(TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.addCleanup(self.loop.close)
        self.host = NativeNavigationHost(DESTINATION_ITEMS)
        self.app = SimpleNamespace(loop=self.loop, native_host=self.host, active_host=True,
            select_destination=Mock(return_value=True), adaptive=SimpleNamespace(render=Mock()))
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
        self.assertNotIn(self.header.parent_button, self.header.children)
        nav = self.navigation[self.host.destinations.index('files')]
        nav.viewControllers.pop()
        self.routes.native_popped(nav)
        self.finish()
        self.assertEqual(self.loaded, [('Local files', 'Projects')])
        self.assertIs(self.routes.body().children[0], self.view)
        self.routes.back()
        self.finish()
        self.assertEqual(self.loaded[-1], ('Local files', ''))
        self.routes.back()
        self.assertFalse(self.routes.screens['files'])
        self.assertEqual(self.host.state.destination, 'files')

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

    def test_home_import_reveals_file_in_workspaces_and_keeps_reader(self):
        from logisticsmobile.document_sources import folder_action, show_in_folder
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
        from Mobile.tests.test_storage_reader_opening import ReaderClient
        from logisticsmobile.document_sources import show_in_folder
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
        from Mobile.tests.test_remote_readers import RemoteClient
        from logisticsmobile.document_sources import show_in_folder, folder_action
        app = self.app
        app.cloud_client = client = RemoteClient()
        app.cloud_remote.items = ['Files']
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
        from logisticsmobile.document_sources import folder_action, show_in_folder
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
