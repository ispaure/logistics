"""Retained imports are measurable and can be deleted independently of sources."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from commonUtils.runtime.resources.documents import LocalDocuments
from mobile.app import LogisticsMobile
from mobile.library import LibraryStore
from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books


class SavedFilesTests(unittest.TestCase):
    def drain(self, app):
        async def finish():
            while pending := [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]:
                await asyncio.gather(*pending)
        app.loop.run_until_complete(finish())

    def test_inventory_counts_closed_and_incomplete_imports_and_checks_links(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.cbz'
            source.write_bytes(b'original')
            store = LibraryStore(root / 'Library')
            key, broken = 'a' * 32, 'b' * 32
            store.path(key, '.cbz').write_bytes(b'archive')
            store.path(key, '.json').write_text('invalid record')
            store.edit_journal(key).write_text('interrupted edit')
            store.path(broken, '.cbz').symlink_to(source)
            items, failures = store.stored_files()
            self.assertEqual([item['id'] for item in items], [key])
            self.assertEqual(items[0]['size'], len(b'archiveinvalid record'))
            self.assertEqual(len(failures), 1)
            with self.assertRaises(ValueError):
                store.delete_local_copy(broken)
            store.delete_local_copy(key)
            self.assertFalse(store.path(key, '.cbz').exists())
            self.assertFalse(store.path(key, '.json').exists())
            self.assertFalse(store.edit_journal(key).exists())
            self.assertEqual(source.read_bytes(), b'original')

    def test_delete_closes_reader_forgets_recent_and_preserves_other_import_and_source(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            LogisticsMobile.storage_root = root / 'app'
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
            fixtures = root / 'fixtures'
            fixtures.mkdir()
            epub, comic = make_books(fixtures)
            manager = app.reader_manager()
            store = manager.catalog.library_store
            record = store.import_book(LocalDocuments(), comic)
            other = store.import_book(LocalDocuments(), epub)
            from mobile.resource_imports import ResourceImports
            # A retained local source gets imported once; deleting that import
            # must allow importing the source again instead of a stale reopen.
            source = app.private_root / 'retained.cbz'
            source.write_bytes(comic.read_bytes())
            imports = ResourceImports(app.private_root)
            imports.remember(source, 'library', record['id'])
            items, failures = store.stored_files()
            self.assertEqual(failures, [])
            self.assertEqual(sum(item['size'] for item in items), sum(
                path.stat().st_size for path in store.root.iterdir()
                if path.suffix in {'.json', '.cbz', '.epub'}))
            app.loop.run_until_complete(app.open_book(record['id']))
            self.assertTrue(any(item['resource'] == record['id'] for item in app.recent_documents.items))
            app.show_saved_files()
            self.assertIn('2 saved file(s)', app.saved_files_summary.text)
            with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=False)):
                app.loop.run_until_complete(app.delete_saved_file(record['id']))
            self.assertTrue(store.path(record['id'], '.cbz').exists())
            with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)):
                app.loop.run_until_complete(app.delete_saved_file(record['id']))
            self.assertFalse(store.path(record['id'], '.cbz').exists())
            self.assertFalse(store.path(record['id'], '.json').exists())
            self.assertFalse(any(session.resource == record['id'] for session in app.workspace.sessions.values()))
            self.assertFalse(any(item['resource'] == record['id'] for item in app.recent_documents.items))
            self.assertTrue(store.path(other['id'], '.epub').exists())
            self.assertTrue(comic.exists())
            self.assertTrue(source.exists())
            self.assertIsNone(ResourceImports(app.private_root).find(source))
            self.assertIn('1 saved file(s)', app.saved_files_summary.text)
            self.drain(app)

    def test_delete_all_confirms_once_and_preserves_sources_and_local_folders(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            LogisticsMobile.storage_root = root / 'app'
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
            fixtures = root / 'fixtures'
            fixtures.mkdir()
            epub, comic = make_books(fixtures)
            store = app.reader_manager().catalog.library_store
            records = [store.import_book(LocalDocuments(), source) for source in (epub, comic)]
            app.loop.run_until_complete(app.open_book(records[0]['id']))
            from features.rclone.mobile.storage_location import collection_path
            local = collection_path(app.private_root) / 'retained'
            local.mkdir(parents=True)
            (local / 'note.txt').write_text('keep')
            with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=False)):
                app.loop.run_until_complete(app.delete_all_saved_files())
            self.assertEqual(len(store.stored_files()[0]), 2)
            async def becomes_busy(dialog):
                app.reader_manager().catalog.book_busy = True
                return True
            with patch.object(app.main_window, 'dialog', new=AsyncMock(side_effect=becomes_busy)):
                app.loop.run_until_complete(app.delete_all_saved_files())
            self.assertEqual(len(store.stored_files()[0]), 2)
            app.reader_manager().catalog.book_busy = False
            with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)) as dialog:
                app.loop.run_until_complete(app.delete_all_saved_files())
                dialog.assert_awaited_once()
            self.assertEqual(store.stored_files(), ([], []))
            self.assertFalse(any(session.provider == 'library' for session in app.workspace.sessions.values()))
            self.assertFalse(app.recent_documents.items)
            self.assertTrue(epub.exists())
            self.assertTrue(comic.exists())
            self.assertEqual((local / 'note.txt').read_text(), 'keep')
            self.assertIn('2 local copies deleted', app.saved_files_status.text)
            self.drain(app)

    def test_remote_preview_never_becomes_a_saved_import_or_recent_after_restart(self):
        from mobile_build.tests.reading.test_remote_readers import RemoteClient
        from features.rclone.mobile.remote_readers import RemoteReaders
        for remote in ('Cloud', 'Secret'):
            with self.subTest(remote=remote), TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                LogisticsMobile.storage_root = root / 'app'
                self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
                app = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
                fixtures = root / 'fixtures'
                fixtures.mkdir()
                _, comic = make_books(fixtures)
                client = app.cloud_client = RemoteClient()
                name = 'private-remote-comic.cbz'
                client.files[name] = comic.read_bytes()
                async def exercise():
                    app.show_cloud(present=False)
                    self.assertTrue(await app.open_crypt(copies=RemoteReaders(client, remote), key=name))
                    app.save_workspace()
                    self.assertEqual(app.reader_manager().catalog.library_store.stored_files()[0], [])
                    self.assertEqual(app.recent_documents.items, [])
                    for path in app.private_root.rglob('*'):
                        if path.is_file():
                            self.assertNotIn(name.encode(), path.read_bytes())
                            self.assertNotEqual(path.suffix, '.cbz')
                    key = app.private_sessions.active.session.id
                    self.assertTrue(app.private_sessions.close(key))
                    self.assertFalse(client.cached)
                app.loop.run_until_complete(exercise())
                self.drain(app)
                app.main_window.close()
                app.loop.close()
                reopened = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
                self.assertEqual(reopened.recent_documents.items, [])
                self.assertFalse(any(session.provider == 'provider-session'
                                     for session in reopened.workspace.sessions.values()))
                self.assertEqual(reopened.reader_manager().catalog.library_store.stored_files()[0], [])
                self.drain(reopened)
                reopened.main_window.close()
                reopened.loop.close()

    def test_delete_refuses_other_windows_and_busy_readers(self):
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory).resolve()
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
            app.show_saved_files()
            app.scene_manager.owners.hosts['other'] = object()
            app.loop.run_until_complete(app.delete_saved_file('a' * 32))
            self.assertIn('Close other app windows', app.saved_files_status.text)
            app.scene_manager.owners.hosts.pop('other')
            app.reader_manager().catalog.book_busy = True
            app.loop.run_until_complete(app.delete_saved_file('a' * 32))
            self.assertIn('Wait for the reader', app.saved_files_status.text)
            self.drain(app)
