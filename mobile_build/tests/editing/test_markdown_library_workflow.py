"""Library authoring, safe return and remote command rejection."""
from unittest.mock import AsyncMock, patch
import unittest
import mobile_build.tests.documents.test_obsidian as fixtures
from mobile.obsidian import open_vault


class MarkdownLibraryWorkflowTests(unittest.TestCase):
    setUp = fixtures.ObsidianTests.setUp
    tearDown = fixtures.ObsidianTests.tearDown
    run_async = fixtures.ObsidianTests.run_async
    def test_edit_enters_formatted_and_saved_return_refreshes_the_note(self):
        async def exercise():
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            await library.open_note('Vault/Home.md')
            self.assertTrue(await library.open_editor())
            editor = self.app.private_sessions.active
            workflow = editor._provider_markdown
            self.assertEqual(editor.crypt_content.children, [workflow.formatted.view])
            editor.crypt_text.value = '# Saved from library\n'
            await editor.save_crypt()
            back = dict(workflow.actions_menu.actions)['Return to Notes Library']
            await back()
            self.assertEqual(library.path, 'Vault/Home.md')
            self.assertEqual((self.vault / 'Home.md').read_text(), '# Saved from library\n')
            from mobile.routes import contains
            self.assertTrue(contains(self.app.body, library.view))
            self.assertNotIn(editor.session.id, self.app.workspace.sessions)
        self.run_async(exercise())

    def test_cancel_and_failed_save_retain_the_library_draft(self):
        async def exercise():
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            await library.open_note('Vault/Home.md')
            await library.open_editor()
            editor = self.app.private_sessions.active
            editor.crypt_text.value = '# Unsaved\n'
            back = dict(editor._provider_markdown.actions_menu.actions)['Return to Notes Library']
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='cancel')):
                await back()
            self.assertIn(editor.session.id, self.app.workspace.sessions)
            self.assertEqual(editor.crypt_text.value, '# Unsaved\n')
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='save')), \
                 patch.object(editor._crypt_reader_store, 'save', side_effect=OSError('Disk full')):
                await back()
            self.assertIn(editor.session.id, self.app.workspace.sessions)
            self.assertEqual(editor.crypt_text.value, '# Unsaved\n')
            self.assertIn('Disk full', editor.crypt_title.text)
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='discard')):
                await back()
            self.assertNotIn(editor.session.id, self.app.workspace.sessions)
        self.run_async(exercise())

    def test_remote_library_cannot_invoke_edit_or_create_even_directly(self):
        self.provider.remote_storage = True
        async def exercise():
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            await library.open_note('Vault/Home.md')
            self.assertFalse(library.edit.enabled)
            self.assertIsNone(library.edit.parent)
            self.assertNotIn('New note…', dict(library.reader_actions.actions))
            self.assertFalse(await library.open_editor())
            self.assertFalse(library.new_note())
            with self.assertRaisesRegex(ValueError, 'read-only'):
                library.library.create('Cloud mutation')
        self.run_async(exercise())

    def test_create_is_contained_and_never_overwrites_an_existing_note(self):
        from features.text_editor.notes import NotesLibrary
        model = NotesLibrary(self.provider, 'Vault')
        path = model.create('New note', 'Vault/Projects')
        self.assertEqual(path, 'Vault/Projects/New note.md')
        self.assertEqual(model.read(path), b'')
        with self.assertRaises(FileExistsError):
            model.create('New note', 'Vault/Projects')
        for name in ('../Escape', '.hidden', 'bad/name'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                model.create(name)
        with self.assertRaises(ValueError):
            model.image_source('Vault/Home.md')('../outside.png')
