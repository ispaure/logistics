import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch
from logisticsmobile.app import LogisticsMobile


class FileUITests(unittest.TestCase):
    def test_local_delete_confirmation_and_save_as_retarget(self):
        class Client:
            def crypt_remotes(self): return []
            def cancel(self): pass
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory).resolve()
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
            try:
                app.cloud_client = Client()
                app.show_cloud()
                app.loop.run_until_complete(app.show_files())
                root = app.private_root / 'LocalFiles'
                (root / 'remove.txt').write_text('delete fixture')
                app.loop.run_until_complete(app.browse_files())
                app.file_selection.value = next(iter(app.file_rows))
                with patch.object(app.main_window, 'dialog', AsyncMock(return_value=False)):
                    app.loop.run_until_complete(app.delete_file())
                self.assertTrue((root / 'remove.txt').exists())
                with patch.object(app.main_window, 'dialog', AsyncMock(return_value=True)):
                    app.loop.run_until_complete(app.delete_file())
                self.assertFalse((root / 'remove.txt').exists())
                app.new_document()
                app.editor.value = 'ordinary draft saved through provider'
                app.loop.run_until_complete(app.show_document_save_as())
                app.save_as_name.value = 'saved.md'
                app.loop.run_until_complete(app.save_text_destination())
                self.assertEqual((root / 'saved.md').read_text(), 'ordinary draft saved through provider')
                app.crypt_text.value = 'updated at the new destination'
                app.loop.run_until_complete(app.save_crypt())
                self.assertEqual((root / 'saved.md').read_text(), 'updated at the new destination')
                app.crypt_text.value = 'keep this draft when reopening fails'
                previous = app.crypt_reader
                app.loop.run_until_complete(app.show_crypt_save_as())
                app.save_as_name.value = 'published-but-not-reopened.md'
                with patch('logisticsmobile.file_resources.LocalTextCopies.open', side_effect=OSError('injected reopen failure')):
                    app.loop.run_until_complete(app.save_text_destination())
                self.assertEqual((root / 'published-but-not-reopened.md').read_text(), 'keep this draft when reopening fails')
                self.assertIs(app.crypt_reader, previous)
                self.assertEqual(app.crypt_text.value, 'keep this draft when reopening fails')
                self.assertIsNotNone(app.save_as_data)
                self.assertIn('was saved', app.save_as_status.value)
                app.save_as_name.value = 'changed-before-reopen.md'
                from logisticsmobile.file_resources import LocalTextCopies
                original_open = LocalTextCopies.open
                def changed_open(copies, key, **kwargs):
                    (copies.provider.root / key).write_text('external replacement')
                    return original_open(copies, key, **kwargs)
                with patch.object(LocalTextCopies, 'open', changed_open):
                    app.loop.run_until_complete(app.save_text_destination())
                self.assertIs(app.crypt_reader, previous)
                self.assertEqual(app.crypt_text.value, 'keep this draft when reopening fails')
                self.assertIn('was saved', app.save_as_status.value)
                app.save_as_name.value = 'published-but-ui-failed.md'
                with patch.object(app, '_show_crypt_content', side_effect=ValueError('injected widget failure')):
                    app.loop.run_until_complete(app.save_text_destination())
                self.assertIs(app.crypt_reader, previous)
                self.assertEqual(app.crypt_text.value, 'keep this draft when reopening fails')
                self.assertIsNotNone(app.save_as_data)
                app.save_as_name.value = 'published-but-navigation-refused.md'
                with patch.object(app, 'show_view', return_value=False):
                    app.loop.run_until_complete(app.save_text_destination())
                self.assertIs(app.crypt_reader, previous)
                self.assertEqual(app.crypt_text.value, 'keep this draft when reopening fails')
                app.clear_private_reader(discard=True)

            finally:
                app.main_window.close()
                app.loop.close()

    def test_tap_folders_back_history_search_sort_and_failed_navigation(self):
        class Client:
            def crypt_remotes(self): return []
            def cancel(self): pass
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory).resolve()
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
            async def check():
                app.cloud_client = Client()
                app.show_cloud()
                await app.show_files()
                root = app.private_root / 'LocalFiles'
                (root / 'books').mkdir()
                (root / 'books/page2.md').write_text('two')
                (root / 'books/page10.md').write_text('ten ten')
                await app.browse_files()
                browser = app.file_browser
                folder = next(entry for entry in browser.entries if entry.container)
                await browser.buttons[folder.identity].on_press()
                self.assertEqual(app.file_path, 'books')
                self.assertTrue(browser.back_button.enabled)
                self.assertEqual([entry.label for entry in browser.entries], ['page2.md', 'page10.md'])
                browser.sort.value = 'Size largest'
                self.assertEqual([entry.label for entry in browser.entries], ['page10.md', 'page2.md'])
                first = browser.entries[0]
                await browser.buttons[first.identity].on_press()
                browser.search.value = 'PAGE2'
                self.assertEqual([entry.label for entry in browser.entries], ['page2.md'])
                with self.assertRaises(ValueError):
                    app.selected_file()
                await browser.back_button.on_press()
                self.assertEqual(app.file_path, '')
                self.assertEqual(browser.search.value, '')
                self.assertFalse(browser.back_button.enabled)
                await browser.buttons[folder.identity].on_press()
                (root / 'books/sub').mkdir()
                (root / 'books/sub/nested.md').write_text('nested')
                browser.search_button.on_press()
                browser.search.value = 'nested'
                await __import__('asyncio').gather(*tuple(browser.tasks))
                self.assertEqual([entry.label for entry in browser.entries], ['sub/nested.md'])
                await browser.buttons[browser.entries[0].identity].on_press()
                self.assertEqual(app.selected_file()[1], 'books/sub/nested.md')
                browser.close_search_button.on_press()
                old_history = list(browser.history.locations)
                # Failed directory loads leave the existing listing and history usable.
                app.file_location.value = 'missing'
                self.assertFalse(await app.browse_files())
                self.assertEqual(app.file_path, 'books')
                self.assertEqual(app.file_location.value, 'books')
                self.assertEqual(browser.history.locations, old_history)
                await app.show_editor_browser('open')
                editor = app.editor_browser
                folder = next(entry for entry in editor.entries if entry.container)
                await editor.buttons[folder.identity].on_press()
                self.assertEqual(app.picker_folder.value, 'books')
                editor.search.value = 'page10'
                await editor.buttons[editor.entries[0].identity].on_press()
                self.assertEqual(app.save_as_name.value, 'page10.md')
                await editor.back_button.on_press()
                self.assertEqual(app.picker_folder.value, '')
                await browser.close()
                await editor.close()
            try:
                app.loop.run_until_complete(check())
            finally:
                app.main_window.close()
                app.loop.close()
