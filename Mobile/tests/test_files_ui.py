from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch
from logisticsmobile.app import LogisticsMobile


class FileUITests(unittest.TestCase):
    def test_cold_local_files_open_while_initial_cloud_restore_is_blocked(self):
        import asyncio
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory).resolve()
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.assertFalse(app.cloud_busy)
            self.assertIsNone(app.cloud_client)
            self.assertFalse(hasattr(app, 'cloud_view'))
            release = asyncio.Event()
            original = app.show_cloud
            def initialize(*args, **kwargs):
                original(*args, **kwargs)
                async def restore():
                    await release.wait()
                app.cloud_restore_task = asyncio.create_task(restore())
            async def exercise():
                try:
                    with patch.object(app, 'show_cloud', side_effect=initialize):
                        await asyncio.wait_for(app.show_files(), 1)
                    self.assertFalse(app.cloud_restore_task.done())
                    self.assertIn('Local files', [row.value for row in app.file_storage.items])
                    self.assertIsNotNone(app.file_browser)
                finally:
                    release.set()
                    await app.cloud_restore_task
            try:
                app.loop.run_until_complete(exercise())
            finally:
                app.main_window.close()
                app.loop.close()

    def test_encrypted_provider_reads_during_transfer_without_allowing_mutations(self):
        from features.rclone.localcrypt.mobile.resources import CryptFiles
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory).resolve()
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                app.show_cloud(present=False)
                app.loop.run_until_complete(app.show_files())
                provider = object.__new__(CryptFiles)
                provider.root, provider.client = Path(directory), object()
                app.file_provider = provider
                app.file_rows = {'note': {'path': 'note.md', 'name': 'note.md', 'directory': False}}
                app.file_selection.items = ['note']
                app.file_selection.value = 'note'
                app.cloud_busy = app.transfer_busy = True
                with patch.object(CryptFiles, 'entry', return_value={'directory': False}), patch.object(
                        app, 'open_crypt', new_callable=AsyncMock) as opened:
                    app.loop.run_until_complete(app.read_managed_file())
                    opened.assert_awaited_once()
                    self.assertTrue(opened.call_args.kwargs['copies'].offline)
                mutation = unittest.mock.Mock()
                self.assertFalse(app.loop.run_until_complete(app.file_work(mutation)))
                mutation.assert_not_called()
                self.assertTrue(app.cloud_busy and app.transfer_busy)
                # Pulled providers carry their own namespace. Browsing and
                # editor picking must return that same object, not reconstruct
                # one from its display label and lose the association.
                label = 'LocalCrypt: Fixture (pulled)'
                app.file_roots = app.editor_storage_roots = {label: provider}
                self.assertIs(app.file_provider_for(label), provider)
                self.assertIs(app.editor_provider(label), provider)
            finally:
                app.cloud_busy = app.transfer_busy = False
                app.main_window.close()
                app.loop.close()

    def test_superseded_host_ignores_late_folder_results_and_errors(self):
        import asyncio
        from threading import Event
        from commonUtils.runtime.local_files import LocalFiles
        for failed in (False, True):
            with self.subTest(failed=failed), TemporaryDirectory() as directory:
                LogisticsMobile.storage_root = Path(directory).resolve()
                self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
                app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
                replacement = None
                started, release = Event(), Event()
                original = LocalFiles.list
                def delayed(provider, *args, **kwargs):
                    started.set()
                    if not release.wait(5):
                        raise RuntimeError('Folder fixture was not released')
                    if failed:
                        raise OSError('Late folder failure')
                    return original(provider, *args, **dict(kwargs, cancelled=lambda: False))
                async def exercise():
                    nonlocal replacement
                    app.show_cloud(present=False)
                    await app.show_files()
                    status = app.file_status.value
                    with patch.object(type(app.file_provider), 'list', new=delayed), patch.object(app, 'populate_file_browser') as publish:
                        task = asyncio.create_task(app.browse_files())
                        try:
                            for _ in range(100):
                                if started.is_set():
                                    break
                                await asyncio.sleep(.01)
                            self.assertTrue(started.is_set())
                            replacement = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
                            self.assertFalse(app.active_host)
                            body = replacement.body
                            release.set()
                            self.assertFalse(await task)
                            publish.assert_not_called()
                            self.assertEqual(app.file_status.value, status)
                            self.assertIs(replacement.body, body)
                        finally:
                            release.set()
                            await task
                try:
                    app.loop.run_until_complete(exercise())
                finally:
                    hosts = [app, *([replacement] if replacement is not None else [])]
                    for host in hosts:
                        host.main_window.close()
                    for loop in {host.loop for host in hosts}:
                        if not loop.is_closed():
                            loop.close()

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
                app.provider_sessions().active.crypt_text.value = 'updated at the new destination'
                app.loop.run_until_complete(app.save_crypt())
                self.assertEqual((root / 'saved.md').read_text(), 'updated at the new destination')
                app.provider_sessions().active.crypt_text.value = 'keep this draft when reopening fails'
                previous = (app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None)
                app.loop.run_until_complete(app.show_crypt_save_as())
                app.save_as_name.value = 'published-but-not-reopened.md'
                with patch('features.text_editor.resources.LocalTextCopies.open', side_effect=OSError('injected reopen failure')):
                    app.loop.run_until_complete(app.save_text_destination())
                self.assertEqual((root / 'published-but-not-reopened.md').read_text(), 'keep this draft when reopening fails')
                self.assertIs((app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None), previous)
                self.assertEqual(app.provider_sessions().active.crypt_text.value, 'keep this draft when reopening fails')
                self.assertIsNotNone(app.save_as_data)
                self.assertIn('was saved', app.save_as_status.value)
                app.save_as_name.value = 'changed-before-reopen.md'
                from features.text_editor.resources import LocalTextCopies
                original_open = LocalTextCopies.open
                def changed_open(copies, key, **kwargs):
                    (copies.provider.root / key).write_text('external replacement')
                    return original_open(copies, key, **kwargs)
                with patch.object(LocalTextCopies, 'open', changed_open):
                    app.loop.run_until_complete(app.save_text_destination())
                self.assertIs((app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None), previous)
                self.assertEqual(app.provider_sessions().active.crypt_text.value, 'keep this draft when reopening fails')
                self.assertIn('was saved', app.save_as_status.value)
                app.save_as_name.value = 'published-but-ui-failed.md'
                with patch.object(app, '_show_crypt_content', side_effect=ValueError('injected widget failure')):
                    app.loop.run_until_complete(app.save_text_destination())
                self.assertIs((app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None), previous)
                self.assertEqual(app.provider_sessions().active.crypt_text.value, 'keep this draft when reopening fails')
                self.assertIsNotNone(app.save_as_data)
                app.save_as_name.value = 'published-but-navigation-refused.md'
                with patch.object(app, 'show_view', return_value=False):
                    app.loop.run_until_complete(app.save_text_destination())
                self.assertIs((app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None), previous)
                self.assertEqual(app.provider_sessions().active.crypt_text.value, 'keep this draft when reopening fails')
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
                await browser.activate_entry(folder)
                self.assertEqual(app.file_path, 'books')
                self.assertTrue(browser.back_button.enabled)
                self.assertEqual([entry.label for entry in browser.entries], ['page2.md', 'page10.md'])
                browser.sort.value = 'Size largest'
                self.assertEqual([entry.label for entry in browser.entries], ['page10.md', 'page2.md'])
                first = browser.entries[0]
                await browser.activate_entry(first)
                browser.search.value = 'PAGE2'
                while browser.tasks:
                    await __import__('asyncio').gather(*tuple(browser.tasks))
                self.assertEqual([entry.label for entry in browser.entries], ['page2.md'])
                with self.assertRaises(ValueError):
                    app.selected_file()
                await browser.back_button.on_press()
                self.assertEqual(app.file_path, '')
                self.assertEqual(browser.search.value, '')
                self.assertFalse(browser.back_button.enabled)
                folder = next(entry for entry in browser.entries if entry.container)
                await browser.activate_entry(folder)
                (root / 'books/sub').mkdir()
                (root / 'books/sub/nested.md').write_text('nested')
                browser.search_button.on_press()
                browser.search.value = 'nested'
                while browser.tasks:
                    await __import__('asyncio').gather(*tuple(browser.tasks))
                self.assertEqual([entry.label for entry in browser.entries], ['sub/nested.md'])
                await browser.activate_entry(browser.entries[0])
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
                await editor.activate_entry(folder)
                self.assertEqual(app.picker_folder.value, 'books')
                editor.search.value = 'page10'
                editor.render()  # Tap a row from the rendered query snapshot.
                await editor.activate_entry(editor.entries[0])
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
