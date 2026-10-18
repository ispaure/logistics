"""Visible file/library actions retain source identity, drafts and private cleanup."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from logisticsmobile.app import LogisticsMobile


class MobileWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        LogisticsMobile.storage_root = Path(self.directory.name)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.app.show_documents()
        self.app.show_cloud(present=False)

    def tearDown(self):
        self.app.main_window.close()
        self.app.loop.close()
        LogisticsMobile.storage_root = None
        self.directory.cleanup()

    def test_browser_back_keeps_folder_listing_and_open_sessions(self):
        import base64
        from zipfile import ZipFile
        app = self.app
        app.loop.run_until_complete(app.show_files())
        root = app.private_root / 'LocalFiles' / 'Shelf'
        root.mkdir()
        (root / 'Notes.md').write_text('# Keep my draft')
        with ZipFile(root / 'Comic.cbz', 'w') as archive:
            archive.writestr('page.webp', base64.b64decode('UklGRhwAAABXRUJQVlA4TA8AAAAvAYAAEAcQ/Y8CBiKi/wEA'))
        app.loop.run_until_complete(app.browser_file_location(('Local files', 'Shelf')))
        browser = app.file_browser
        panel, tree = app.body, browser.tree
        for filename in ('Comic.cbz', 'Notes.md', 'Comic.cbz'):
            browser.search.value = filename
            entry = next(item for item in browser.entries if item.label == filename)
            app.loop.run_until_complete(browser._select_pressed(entry, browser.buttons[entry.identity]))
            self.assertEqual(app.native_host.state.destination, 'files')
            owner = app.readers.active if filename.endswith('.cbz') else app.private_sessions.active
            if filename.endswith('.md'):
                owner.crypt_text.value = '# Unsaved browser draft'
            self.assertTrue(app.routes.back())
            self.assertIs(app.body, panel)
            self.assertIs(browser.tree, tree)
            self.assertEqual(app.file_path, 'Shelf')
            self.assertEqual(browser.search.value, filename)
            self.assertIn(owner.session.id, app.workspace.sessions)
            self.assertFalse(getattr(app, '_comic_chrome_hidden', False))
        note = next(owner for owner in app.private_sessions.controllers.values() if owner.session.title == 'Notes.md')
        self.assertEqual(note.crypt_text.value, '# Unsaved browser draft')
        # Explicitly reopening through Open documents uses that destination.
        self.assertTrue(app.private_sessions.activate(note.session.id))
        self.assertEqual(app.native_host.state.destination, 'documents')

    def test_downloaded_text_back_uses_its_files_origin(self):
        app = self.app
        app.show_cloud()
        panel = app.body
        path = app.downloads.root / 'Downloaded.txt'
        path.write_text('Downloaded text')
        for _ in range(2):
            app.loop.run_until_complete(app.open_download(path=path))
            self.assertEqual(app.native_host.state.destination, 'files')
            self.assertTrue(app.routes.back())
            self.assertIs(app.body, panel)

    def test_reader_tools_back_returns_to_reader_then_origin_folder(self):
        from io import BytesIO
        from zipfile import ZipFile
        from PIL import Image
        app = self.app
        app.loop.run_until_complete(app.show_files())
        root = app.private_root / 'LocalFiles'
        page = BytesIO()
        Image.new('RGB', (2, 3)).save(page, format='WEBP')
        with ZipFile(root / 'Comic.cbz', 'w') as archive:
            archive.writestr('page.webp', page.getvalue())
        app.loop.run_until_complete(app.browse_files())
        folder_panel = app.body
        browser = app.file_browser
        entry = next(item for item in browser.entries if item.label == 'Comic.cbz')
        app.loop.run_until_complete(browser._select_pressed(entry, browser.buttons[entry.identity]))
        owner = app.readers.active
        reader_panel = app.body
        owner.show_reader_tools()
        self.assertIsNot(app.body, reader_panel)
        self.assertTrue(app.routes.back())
        self.assertIs(app.body, reader_panel)
        self.assertIn(owner.library_view, app.body.children)
        self.assertTrue(app.routes.back())
        self.assertIs(app.body, folder_panel)
        self.assertFalse(hasattr(app, 'book_reader'))
        self.assertFalse(hasattr(app, 'library_store'))

    def test_tapping_file_opens_correct_provider_preview_keeps_draft_and_close_clears_it(self):
        app = self.app
        app.loop.run_until_complete(app.show_files())
        root = app.private_root / 'LocalFiles'
        (root / 'Notes.md').write_text('# Original\n')
        app.loop.run_until_complete(app.browse_files())
        browser = app.file_browser
        entry = next(item for item in browser.entries if item.label == 'Notes.md')
        app.loop.run_until_complete(browser._select_pressed(entry, browser.buttons[entry.identity]))
        owner = app.private_sessions.active
        self.assertEqual(owner.crypt_reader.name, 'Notes.md')
        self.assertEqual(app.native_host.state.destination, 'files')
        self.assertEqual(owner.crypt_content.children, [owner.crypt_preview])
        self.assertIn(owner.markdown_speech.button, owner.reader_toolbar.children)
        owner.toggle_private_preview()
        self.assertEqual(owner.crypt_content.children, [owner.crypt_formatted.view])
        owner.crypt_text.value = '# Unsaved draft\n'
        owner.toggle_private_preview()
        self.assertEqual(owner.crypt_content.children, [owner.crypt_preview])
        self.assertIn(owner.markdown_speech.button, owner.reader_toolbar.children)
        self.assertEqual(owner.crypt_text.value, '# Unsaved draft\n')
        app.show_settings()
        self.assertNotIn(owner.crypt_preview, owner.crypt_content.children)
        self.assertEqual(owner.crypt_text.value, '# Unsaved draft\n')
        self.assertEqual((root / 'Notes.md').read_text(), '# Original\n')
        app.private_sessions.activate(owner.session.id)
        owner.toggle_private_preview()
        self.assertTrue(app.private_sessions.close(owner.session.id, discard=True))
        self.assertEqual(owner.crypt_text.value, '')
        self.assertNotIn(owner.crypt_preview, owner.crypt_content.children)

    def test_local_browsing_during_pull_preserves_transfer_cancel_and_the_writer(self):
        import asyncio
        from threading import Event
        from test_mirror_jobs import MirrorClient
        app = self.app
        started, release = Event(), Event()
        class Client(MirrorClient):
            def crypt_remotes(self): return []
            def restore(self, **kwargs): return []
            def cancel(self): release.set()
            def copy_remote_file(self, path, stream):
                started.set()
                if not release.wait(30):
                    raise RuntimeError('Pull fixture was not released')
                return super().copy_remote_file(path, stream)
        app.cloud_client = Client()
        root = app.private_root / 'LocalFiles' / 'Reference'
        root.mkdir(parents=True)
        (root / 'Notes.md').write_text('Unrelated local note')
        (root / 'Plain.txt').write_text('A plain local text file')
        (root / 'Invalid.txt').write_bytes(b'\xff')
        import base64
        from zipfile import ZipFile
        webp = base64.b64decode('UklGRhwAAABXRUJQVlA4TA8AAAAvAYAAEAcQ/Y8CBiKi/wEA')
        with ZipFile(root / 'Comic.cbz', 'w') as archive:
            archive.writestr('page2.webp', webp)
            archive.writestr('page10.webp', webp)
        comic_source = (root / 'Comic.cbz').read_bytes()
        app.editor.value = 'Retain this ordinary draft'
        writer = app.editor_view
        async def exercise():
            task = asyncio.create_task(app.run_mirror_work(lambda client, cancel, progress:
                app.mirror_store().create(client, 'Remote', 'folder', cancelled=cancel, progress=progress), 'create'))
            try:
                for _ in range(100):
                    if started.is_set(): break
                    await asyncio.sleep(.01)
                self.assertTrue(started.is_set())
                cancel = app.transfer_controller()._transfer_cancel
                file_cancel = app._crypt_cancel
                self.assertTrue(app.cloud_busy and app.transfer_busy)
                await app.show_local_location()
                self.assertEqual(app.native_host.state.destination, 'files')
                self.assertTrue(await app.browser_file_location(('Local files', 'Reference')))
                self.assertEqual(set(item.label for item in app.file_browser.entries), {'Notes.md', 'Plain.txt', 'Comic.cbz', 'Invalid.txt'})
                await app.parent_file_folder()
                self.assertEqual(app.file_path, '')
                # Re-enter through the existing view, not just first creation.
                await app.show_local_location()
                self.assertTrue(await app.browser_file_location(('Local files', 'Reference')))
                self.assertIs(app.transfer_controller()._transfer_cancel, cancel)
                self.assertFalse(cancel.is_set())
                self.assertTrue(app.cloud_busy and app.transfer_busy)
                self.assertFalse(app.cloud_remote.enabled)
                self.assertIs(app.editor_view, writer)
                self.assertEqual(writer.document.text, 'Retain this ordinary draft')
                async def tap(name):
                    await app.show_local_location()
                    await app.browser_file_location(('Local files', 'Reference'))
                    browser = app.file_browser
                    entry = next(item for item in browser.entries if item.label == name)
                    await browser._select_pressed(entry, browser.buttons[entry.identity])
                    self.assertIs(app.transfer_controller()._transfer_cancel, cancel, app.transfer_message)
                    self.assertFalse(cancel.is_set())
                    self.assertIs(app._crypt_cancel, file_cancel)
                    self.assertTrue(app.cloud_busy and app.transfer_busy)
                await tap('Notes.md')
                text_owner = app.private_sessions.active
                self.assertEqual(text_owner.crypt_text.value, 'Unrelated local note')
                text_owner.crypt_text.value = '# Draft while pulling'
                await tap('Plain.txt')
                self.assertEqual(app.private_sessions.active.crypt_text.value, 'A plain local text file')
                await tap('Comic.cbz')
                self.assertEqual(app.reader_manager().active.book_reader.pages, ['page2.webp', 'page10.webp'])
                await app.next_book_page()
                self.assertEqual(app.reader_manager().active.book_record['position'], 1)
                await tap('Notes.md')
                self.assertIs(app.private_sessions.active, text_owner)
                self.assertEqual(text_owner.crypt_text.value, '# Draft while pulling')
                owners = set(app.private_sessions.controllers)
                await tap('Invalid.txt')
                self.assertEqual(set(app.private_sessions.controllers), owners)
                self.assertEqual(text_owner.crypt_text.value, '# Draft while pulling')
                self.assertIn('failed', app.cloud_status.value.lower())
                self.assertEqual((root / 'Comic.cbz').read_bytes(), comic_source)
                release.set()
                self.assertTrue(await task)
                self.assertFalse(app.cloud_busy or app.transfer_busy)
                self.assertEqual((root / 'Notes.md').read_text(), 'Unrelated local note')
            finally:
                release.set()
                await task
        app.loop.run_until_complete(exercise())

    def test_hierarchical_rows_work_without_folder_captions_or_selection_ticks(self):
        import toga
        from unittest.mock import AsyncMock
        from commonUtils.runtime.browsing import BrowseTree, BrowseEntry
        from logisticsmobile.browser_ui import FileBrowser
        # Opaque identities exercise a hierarchy independent of disk paths:
        # the same tree contract can represent archive members or JSON nodes.
        opened = AsyncMock()
        browser = FileBrowser(open_folder=opened, preview=False)
        tree = BrowseTree(BrowseEntry('json:root', 'Catalogue', True))
        folder = BrowseEntry('json:books', 'Books', True, payload={'id': 'books'})
        document = BrowseEntry('archive:chapter', 'Chapter.md', properties={'size': 123}, payload={'member': 'Chapter.md'})
        tree.set_children('json:root', [folder, document])
        browser.set_tree(tree)
        labels = [child.text for row in browser.items.children for child in row.children[0].children if isinstance(child, toga.Label)]
        self.assertNotIn('Folder', labels)
        button = browser.buttons[folder.identity]
        async def navigate(payload):
            self.assertFalse(button.text.startswith('✓'))
        opened.side_effect = navigate
        self.app.loop.run_until_complete(browser._select_pressed(folder, button))
        opened.assert_awaited_once_with({'id': 'books'})
        self.app.loop.run_until_complete(browser.select(document))
        self.assertFalse(any(button.text.startswith('✓') for button in browser.buttons.values()))
        self.app.loop.run_until_complete(browser.close())

    def test_delayed_listing_cannot_replace_a_newer_folder(self):
        from unittest.mock import patch
        app = self.app
        app.loop.run_until_complete(app.show_files())
        root = app.private_root / 'LocalFiles'
        (root / 'Older').mkdir()
        (root / 'Older' / 'Old.txt').write_text('old')
        (root / 'Newer').mkdir()
        (root / 'Newer' / 'New.txt').write_text('new')
        async def exercise():
            app.file_location.value = 'Older'
            async def delayed(work, **kwargs):
                work(lambda: False)
                app.cloud_busy = True
                app.file_location.value = 'Newer'
                self.assertTrue(await app.browse_local_during_transfer('Newer'))
                app.cloud_busy = False
                return True
            with patch.object(app, 'file_work', side_effect=delayed):
                self.assertFalse(await app.browse_files())
            self.assertEqual(app.file_path, 'Newer')
            self.assertEqual([item.label for item in app.file_browser.entries], ['New.txt'])
        app.loop.run_until_complete(exercise())

    def test_item_menu_selects_the_exact_file_without_opening_or_changing_source(self):
        app = self.app
        app.loop.run_until_complete(app.show_files())
        root = app.private_root / 'LocalFiles'
        (root / 'One.md').write_text('one')
        (root / 'Two.md').write_text('two')
        app.loop.run_until_complete(app.browse_files())
        browser = app.file_browser
        entry = next(item for item in browser.entries if item.label == 'Two.md')
        row = next(row for row in browser.items.children if browser.buttons[entry.identity] in row.children[0].children)
        menu = row.children[0].children[-1]
        app.loop.run_until_complete(menu.on_press())
        self.assertEqual(app.selected_file()[1], 'Two.md')
        self.assertIsNone(getattr(app, 'crypt_reader', None))
        app.show_file_actions(operation='rename')
        self.assertEqual(app.file_name.value, 'Two.md')
        self.assertEqual((root / 'Two.md').read_text(), 'two')


if __name__ == '__main__':
    unittest.main()
