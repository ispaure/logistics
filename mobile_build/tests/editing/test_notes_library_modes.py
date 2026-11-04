"""Native folder choice and Notes Library authoring workflows."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import unittest
import mobile_build.tests.documents.test_obsidian as fixtures
from mobile.obsidian import offer_vault, open_vault


class NotesLibraryModeTests(unittest.TestCase):
    setUp = fixtures.ObsidianTests.setUp
    tearDown = fixtures.ObsidianTests.tearDown
    run_async = fixtures.ObsidianTests.run_async

    def test_search_unopened_folders_with_keywords_and_phrases(self):
        nested = self.vault / 'Projects'
        (nested / 'Wildlife').mkdir()
        (nested / 'Orange.md').write_text('Fruit')
        (nested / 'Wildlife/Orange.md').write_text('Colour')
        (nested / 'Wildlife/Red sea TURTLE.md').write_text('# Title')
        (nested / 'Field guide.md').write_text('The turtle has a red shell.')
        (nested / 'Turtle red folder').mkdir()
        (nested / 'this-follow_this.md').write_text('# Title')
        (nested / 'this other follow this.md').write_text('# Title')
        (self.vault / '.obsidian/red turtle.md').write_text('# Hidden')

        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            owner.search_mode.value = 'Search within Documents'

            async def search(query):
                owner.search.value = query
                await owner.search_task
                return [next(child for child in row.children if hasattr(child, 'vault_path')) for row in owner.rows.children]

            buttons = await search('orange')
            self.assertEqual([button.text for button in buttons],
                             ['Orange.md · Projects', 'Orange.md · Projects/Wildlife'])
            buttons = await search('turtle red')
            self.assertEqual([button.text for button in buttons],
                             ['Red sea TURTLE.md', 'Turtle red folder', 'Field guide.md'])
            with patch.object(owner.library, 'read', side_effect=AssertionError('read note body')):
                owner.search_mode.value = 'Search in File Names'
                self.assertEqual(owner.search.value, '')
                owner.search.value = 'turtle red'
                await owner.search_task
                buttons = [next(child for child in row.children if hasattr(child, 'vault_path')) for row in owner.rows.children]
            self.assertEqual([button.text for button in buttons], ['Red sea TURTLE.md', 'Turtle red folder'])
            self.assertEqual([row.children[0].style.width for row in owner.rows.children], [0, 0])
            self.assertNotIn('Vault/Projects', owner.folders)
            buttons[1].on_press()
            for _ in range(100):
                await asyncio.sleep(.01)
                if owner.selected_path == 'Vault/Projects/Turtle red folder':
                    break
            self.assertEqual(owner.search.value, '')
            self.assertIn('Vault/Projects/Turtle red folder', owner.expanded)
            buttons = await search('"this follow this"')
            self.assertEqual([button.text for button in buttons], ['this-follow_this.md'])
            buttons[-1].on_press()
            for _ in range(100):
                await asyncio.sleep(.01)
                if owner.path:
                    break
            self.assertEqual(owner.path, 'Vault/Projects/this-follow_this.md')

        self.run_async(exercise())

    def test_root_vault_choice_and_bare_wiki_link_to_unloaded_subfolder(self):
        from commonUtils.runtime.resources.local import LocalFiles
        from mobile.preview import markdown_preview
        (self.vault / 'Home.md').write_text('# **[[Tech]]**')
        (self.vault / 'Projects/Tech.md').write_text('# Tech')
        async def exercise():
            provider = LocalFiles(self.vault)
            browser = SimpleNamespace()
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='notes')) as dialog:
                self.assertTrue(await offer_vault(self.app, browser, provider, '', provider.list('')))
                self.assertEqual(dialog.await_count, 1)
            owner = self.app.vault_browser
            self.assertTrue(await owner.open_note('Home.md'))
            self.assertIn('href="Tech"', markdown_preview('# **[[Tech]]**', local_links=True))
            owner.follow_link(owner.web, owner.base + '?target=Tech')
            for _ in range(100):
                if owner.path == 'Projects/Tech.md':
                    break
                await asyncio.sleep(.01)
            self.assertEqual(owner.path, 'Projects/Tech.md', owner.notice.text)
        self.run_async(exercise())

    def test_folder_choice_regular_notes_refresh_and_navigation_away(self):
        async def exercise():
            browser = SimpleNamespace()
            rows = self.provider.list('Vault')
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='files')) as dialog:
                self.assertFalse(await offer_vault(self.app, browser, self.provider, 'Vault', rows))
                self.assertEqual(dialog.await_count, 1)
                self.assertFalse(await offer_vault(self.app, browser, self.provider, 'Vault', rows))
                self.assertEqual(dialog.await_count, 1)
                await offer_vault(self.app, browser, self.provider, '', self.provider.list(''))
                self.assertEqual(dialog.await_count, 1)
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='notes')):
                self.assertTrue(await offer_vault(self.app, browser, self.provider, 'Vault', rows))
                self.assertEqual(self.app.vault_browser.root, 'Vault')
            browser._notes_location = None
            async def leave(dialog):
                self.app.show_documents_hub()
                return 'notes'
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(side_effect=leave)):
                self.assertFalse(await offer_vault(self.app, browser, self.provider, 'Vault', rows))
        self.run_async(exercise())


    def test_workspaces_browse_notes_folders_without_prompt_on_every_visit(self):
        import shutil
        from services.documents.locations import collection_path
        from mobile.routes import contains
        shutil.copytree(self.vault, collection_path(self.app.private_root) / 'Notes')
        async def exercise():
            for cold in (True, False, False):
                if cold:
                    self.app.show_locations()
                else:
                    self.app.routes.back()
                with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='notes')) as dialog:
                    self.assertTrue(await self.app.show_files(location=('Local files', 'Notes')))
                    dialog.assert_not_awaited()
                self.assertEqual(self.app.file_path, 'Notes')
                self.assertTrue(contains(self.app.body, self.app.files_view))
                self.assertIsNotNone(self.app.file_browser.tree)
                self.assertIsNone(getattr(self.app, 'vault_browser', None))
        self.run_async(exercise())

    def test_folder_choice_keeps_parent_contents_until_files_are_chosen(self):
        import shutil
        from services.documents.locations import collection_path
        shutil.copytree(self.vault, collection_path(self.app.private_root) / 'Notes')

        async def exercise():
            await self.app.show_files(local_root=True)
            browser = self.app.file_browser
            parent_tree = browser.tree
            parent_location = self.app.file_loaded_location

            async def choose(dialog):
                self.assertIs(browser.tree, parent_tree)
                self.assertEqual(self.app.file_loaded_location, parent_location)
                self.assertEqual(self.app.file_path, '')
                await asyncio.sleep(0)  # A repaint while the choice is pending.
                self.assertIs(browser.tree, parent_tree)
                return 'files'  # Browse Files

            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(side_effect=choose)):
                self.assertTrue(await self.app.browser_file_location(('Local files', 'Notes')))
            self.assertEqual(self.app.file_path, 'Notes')
            self.assertIsNot(browser.tree, parent_tree)

        self.run_async(exercise())


    def test_repeated_notes_choice_opens_one_library(self):
        async def exercise():
            entered, release = asyncio.Event(), asyncio.Event()
            browser = SimpleNamespace()
            rows = self.provider.list('Vault')
            async def choose(dialog):
                entered.set()
                await release.wait()
                return 'notes'
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(side_effect=choose)) as dialog, \
                    patch('mobile.obsidian.open_vault', new=AsyncMock(return_value=object())) as opened:
                first = asyncio.create_task(offer_vault(self.app, browser, self.provider, 'Vault', rows))
                second = None
                try:
                    await asyncio.wait_for(entered.wait(), 5)
                    second = asyncio.create_task(offer_vault(self.app, browser, self.provider, 'Vault', rows))
                    await asyncio.sleep(0)
                    self.assertFalse(second.done())
                    release.set()
                    self.assertEqual(await asyncio.gather(first, second), [True, True])
                    self.assertEqual(dialog.await_count, 1)
                    opened.assert_awaited_once()
                finally:
                    release.set()
                    await first
                    if second is not None:
                        await second

        self.run_async(exercise())

    def test_cancelled_pending_choice_is_not_treated_as_a_completed_visit(self):
        async def exercise():
            entered = asyncio.Event()
            browser = SimpleNamespace()
            rows = self.provider.list('Vault')
            async def choose(dialog):
                entered.set()
                await asyncio.Event().wait()
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(side_effect=choose)):
                task = asyncio.create_task(offer_vault(self.app, browser, self.provider, 'Vault', rows))
                await asyncio.wait_for(entered.wait(), 5)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='files')) as dialog:
                self.assertFalse(await offer_vault(self.app, browser, self.provider, 'Vault', rows))
                dialog.assert_awaited_once()

        self.run_async(exercise())


    def test_cancelled_same_folder_read_cannot_reset_a_newer_request(self):
        import shutil
        from threading import Event
        from services.documents.locations import collection_path
        shutil.copytree(self.vault, collection_path(self.app.private_root) / 'Notes')

        async def exercise():
            await self.app.show_files(local_root=True)
            provider = self.app.file_provider_for('Local files')
            original = provider.list
            entered = [Event(), Event()]
            release = [Event(), Event()]
            calls = 0
            def slow(path='', **kwargs):
                nonlocal calls
                current = calls
                calls += 1
                entered[current].set()
                release[current].wait(5)
                return original(path, **kwargs)
            async def wait(event):
                for _ in range(100):
                    if event.is_set():
                        return
                    await asyncio.sleep(.01)
                self.fail('Folder read did not start')
            with patch.object(provider, 'list', side_effect=slow), \
                    patch.object(self.app, 'file_provider_for', return_value=provider), \
                    patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='files')):
                first = asyncio.create_task(self.app.browser_file_location(('Local files', 'Notes')))
                second = None
                try:
                    await wait(entered[0])
                    second = asyncio.create_task(self.app.browse_files())
                    await wait(entered[1])
                    release[0].set()
                    self.assertFalse(await first)
                    self.assertEqual(self.app.file_location.value, 'Notes')
                    release[1].set()
                    self.assertTrue(await second)
                    self.assertEqual(self.app.file_path, 'Notes')
                finally:
                    for event in release:
                        event.set()
                    await first
                    if second is not None:
                        await second

        self.run_async(exercise())


    def test_leaving_during_folder_read_does_not_show_a_late_choice(self):
        import shutil
        from threading import Event
        from services.documents.locations import collection_path
        shutil.copytree(self.vault, collection_path(self.app.private_root) / 'Notes')

        async def exercise():
            await self.app.show_files(local_root=True)
            provider = self.app.file_provider_for('Local files')
            original = provider.list
            entered, release = Event(), Event()
            def slow(path='', **kwargs):
                if path == 'Notes':
                    entered.set()
                    release.wait(5)
                return original(path, **kwargs)
            with patch.object(provider, 'list', side_effect=slow), \
                    patch.object(self.app, 'file_provider_for', return_value=provider), \
                    patch.object(self.app.main_window, 'dialog', new=AsyncMock()) as dialog:
                task = asyncio.create_task(self.app.browser_file_location(('Local files', 'Notes')))
                try:
                    for _ in range(100):
                        if entered.is_set():
                            break
                        await asyncio.sleep(.01)
                    self.assertTrue(entered.is_set())
                    self.app.show_documents_hub()
                    release.set()
                    self.assertFalse(await task)
                    dialog.assert_not_awaited()
                    self.assertEqual(self.app.file_path, '')
                    self.assertEqual(self.app.file_location.value, '')
                finally:
                    release.set()
                    await task

        self.run_async(exercise())

    def test_cloud_folder_does_not_offer_library_or_scan_children(self):
        from mobile_build.tests.documents.test_notes_library import Client
        from mobile.routes import contains
        self.app.show_cloud(present=False)
        async def exercise():
            restore = getattr(self.app, 'cloud_restore_task', None)
            if restore is not None:
                await restore
            self.app.cloud_client = Client(self.vault)
            self.app.set_loaded_remote_names(['remote'])
            self.app.cloud_remote.value = 'remote'
            self.app.cloud_location.value = ''
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='notes')):
                await self.app.browse_cloud_path()
            self.assertIsNone(getattr(self.app, 'vault_browser', None))
            self.assertEqual(self.app.cloud_client.calls, [('list', '')])
        self.run_async(exercise())


    def test_notes_keep_an_independent_provider_when_browser_access_closes(self):
        from commonUtils.runtime.resources.local import LocalFiles
        class Reopenable(LocalFiles):
            closed = False
            def reopen(self):
                return Reopenable(self.root)
            def close(self):
                self.closed = True
            def entry(self, path):
                if self.closed:
                    raise ValueError('Closed browser access')
                return super().entry(path)
        async def exercise():
            browser_provider = Reopenable(self.root)
            owner = await open_vault(self.app, browser_provider, 'Vault', 'files')
            self.assertIsNot(owner.provider, browser_provider)
            browser_provider.close()
            self.assertTrue(await owner.open_note('Vault/Home.md'))
            owner.dispose()
            self.assertTrue(owner.provider.closed)
        self.run_async(exercise())

    def test_move_picker_cancel_and_folder_exclusion_preserve_source(self):
        import toga
        from dataclasses import replace
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            created = []
            factory = owner.host.folder_browser
            def supplied_browser(**callbacks):
                browser = factory(**callbacks)
                created.append(browser)
                return browser
            owner.host = replace(owner.host, folder_browser=supplied_browser)
            picker = await owner.move_picker('Vault/Projects')
            browser = picker._folder_browser
            self.assertEqual(created, [browser])
            self.assertIsNone(browser.local_search)
            self.assertIsNone(browser.resource_search)
            paths = [entry.payload['path'] for entry in browser.entries]
            self.assertNotIn('Projects', paths)
            with self.assertRaises(ValueError):
                browser.search_provider.relative('../outside')
            cancel = next(child for child in picker.children if isinstance(child, toga.Button) and child.text == 'Cancel')
            cancel.on_press()
            self.assertIsNone(owner.file_action_view)
            self.assertTrue((self.vault / 'Projects/Plan.MD').exists())
            await browser.on_open_folder({'path': 'Projects'})
            self.assertIsNone(owner.file_action_view)
        self.run_async(exercise())

    def test_create_folder_and_move_note_update_history_and_names(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            await owner.open_note('Vault/Home.md')
            owner.search.value = 'New folder'
            await owner.search_task
            self.assertFalse(owner.search_rows)
            owner.manage_entry(folder=True)
            form = self.app.body
            from mobile.routes import contains
            # The form is nested in the route's scroll container.
            def find(widget, kind):
                if isinstance(widget, kind):
                    return widget
                for child in getattr(widget, 'children', ()):
                    found = find(child, kind)
                    if found is not None:
                        return found
                content = getattr(widget, 'content', None)
                return find(content, kind) if content is not None else None
            import toga
            find(form, toga.TextInput).value = 'New folder'
            button = find(form, toga.Button)
            await button.on_press()
            self.assertTrue((self.vault / 'New folder').is_dir())
            await owner.search_task
            self.assertEqual([row['name'] for row in owner.search_rows], ['New folder'])
            owner.search.value = 'renamed'
            await owner.search_task
            owner.manage_entry(move=True)
            form = self.app.body
            find(form, toga.TextInput).value = 'Renamed.md'
            await find(form, toga.Button).on_press()
            self.assertEqual(owner.path, 'Vault/Renamed.md')
            picker = await owner.move_picker(owner.path)
            browser = picker._folder_browser
            self.assertTrue(browser.entries)
            self.assertTrue(all(entry.container for entry in browser.entries))
            await browser.on_open_folder({'path': 'New folder'})
            move = next(child for child in picker.children if isinstance(child, toga.Button) and child.text == 'Move here')
            await move.on_press()
            await owner.search_task
            self.assertEqual([row['path'] for row in owner.search_rows], ['Vault/New folder/Renamed.md'])
            self.assertEqual(owner.path, 'Vault/New folder/Renamed.md')
            self.assertEqual(owner.history, ['Vault/New folder/Renamed.md'])
            self.assertFalse((self.vault / 'Home.md').exists())
            self.assertEqual(owner.title.text, 'Renamed.md')
            self.assertTrue(contains(self.app.body, owner.view))
        self.run_async(exercise())
