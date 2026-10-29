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
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='cancel')) as dialog:
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

    def test_opening_a_local_workspace_keeps_the_chosen_library_visible(self):
        import shutil
        from services.documents.locations import collection_path
        from mobile.routes import contains
        shutil.copytree(self.vault, collection_path(self.app.private_root) / 'Notes')
        async def exercise():
            await self.app.show_files(local_root=True)
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='notes')) as dialog:
                self.assertTrue(await self.app.show_files(location=('Local files', 'Notes')))
                self.assertEqual(dialog.await_count, 1)
            owner = self.app.vault_browser
            self.assertEqual(owner.root, 'Notes')
            self.assertTrue(contains(self.app.body, owner.view))
        self.run_async(exercise())

    def test_cloud_folder_choice_reuses_listing_and_opens_read_only_notes(self):
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
            owner = self.app.vault_browser
            self.assertFalse(owner.library.writable)
            self.assertTrue(contains(self.app.body, owner.view))
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

    def test_create_folder_and_move_note_update_history_and_names(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            await owner.open_note('Vault/Home.md')
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
            owner.manage_entry(move=True)
            form = self.app.body
            find(form, toga.TextInput).value = 'New folder/Renamed.md'
            await find(form, toga.Button).on_press()
            self.assertEqual(owner.path, 'Vault/New folder/Renamed.md')
            self.assertEqual(owner.history, ['Vault/New folder/Renamed.md'])
            self.assertFalse((self.vault / 'Home.md').exists())
            self.assertEqual(owner.title.text, 'Renamed.md')
            self.assertTrue(contains(self.app.body, owner.view))
        self.run_async(exercise())
