"""Library record caches invalidate on source revisions and expose copies only."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4
from types import SimpleNamespace

from mobile.library import LibraryStore


class LibraryInventoryTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = LibraryStore(Path(directory.name))
        self.key = uuid4().hex
        self.record = dict(schema=1, id=self.key, name='Fixture.epub', kind='epub',
                           revision=0, position=0, bookmarks=[], digest='a' * 64)
        self.path = self.store.path(self.key, '.json')
        self.path.write_text(json.dumps(self.record))

    def test_source_path_validation_and_backfill_preserve_reading_state(self):
        self.store.remember_source(self.key, self.store.root.parent / 'original.epub')
        restored = LibraryStore(self.store.root).read_record(self.key)[0]
        self.assertEqual(restored['position'], self.record['position'])
        self.assertEqual(restored['bookmarks'], self.record['bookmarks'])
        self.assertEqual(restored['source_path'], str(self.store.root.parent / 'original.epub'))
        before = self.path.read_bytes()
        self.store.remember_source(self.key, self.store.path(self.key, '.epub'))
        self.assertEqual(self.path.read_bytes(), before)
        for source in ('relative.epub', 5, ''):
            with self.subTest(source=source), self.assertRaises(ValueError):
                LibraryStore.decode_record(self.key, json.dumps(dict(self.record, source_path=source)).encode())

    def test_warm_scan_reuses_validation_and_returned_records_are_isolated(self):
        self.store.items()
        with patch.object(self.store, 'decode_record', side_effect=AssertionError('Unchanged record')):
            records, warnings = self.store.items()
        self.assertFalse(warnings)
        records[0]['bookmarks'].append(3)
        self.assertEqual(self.store.cached_items()[0][0]['bookmarks'], [])

    def test_read_only_inventory_never_creates_an_edit_journal_directory(self):
        self.assertFalse((self.store.root / '.edits').exists())
        self.assertEqual(len(self.store.items()[0]), 1)
        self.assertFalse((self.store.root / '.edits').exists())

    def test_external_changes_deletion_and_corruption_invalidate_cache(self):
        self.store.items()
        self.record['name'] = 'Renamed.epub'
        self.path.write_text(json.dumps(self.record))
        self.assertEqual(self.store.items()[0][0]['name'], 'Renamed.epub')
        self.path.write_text('broken')
        self.assertTrue(self.store.items()[1])
        self.assertFalse(self.store.cached_items()[0])
        self.path.unlink()
        self.assertEqual(self.store.items(), ([], []))

    def test_discovery_requests_coalesce_and_credentials_or_refresh_invalidate(self):
        from mobile.app import LogisticsMobile
        LogisticsMobile.storage_root = self.store.root / 'App'
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(app.loop.close)
        self.addCleanup(app.main_window.close)
        catalog = app.reader_manager().catalog
        async def exercise(discover):
            await asyncio.gather(*(catalog.refresh_library_folders() for _ in range(20)))
            self.assertEqual(discover.call_count, 1)
            await catalog.refresh_library_folders(widget=object())
            self.assertEqual(discover.call_count, 2)
            app.cloud_client = SimpleNamespace(generation=1, cancel=lambda: None)
            await catalog.refresh_library_folders()
            self.assertEqual(discover.call_count, 3)
            app.cloud_client.generation = 2
            await catalog.refresh_library_folders()
            self.assertEqual(discover.call_count, 4)
            await catalog.metadata_task
        with patch('mobile.library_ui.discover_libraries', return_value=([], 0)) as discover:
            app.loop.run_until_complete(exercise(discover))

    def test_folder_rows_are_recycled_and_lock_retires_private_callbacks(self):
        from mobile.app import LogisticsMobile
        LogisticsMobile.storage_root = self.store.root / 'App'
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(app.loop.close)
        self.addCleanup(app.main_window.close)
        catalog = app.reader_manager().catalog
        async def exercise():
            await catalog.library_scan_task
            await catalog.metadata_task
            local = SimpleNamespace(private=False, root=self.store.root)
            private = SimpleNamespace(private=True, root=self.store.root / 'Private')
            catalog.library_records = [dict(name=f'Library {index}', folder=str(index),
                source='Local', provider=local) for index in range(1000)]
            catalog.library_records.append(dict(name='SESSION-ONLY-SECRET', folder='secret',
                source='LocalCrypt', provider=private, client=app.cloud_client,
                generation=getattr(app.cloud_client, 'generation', None)))
            with patch('features.books.mobile.library.catalog.toga.Button', side_effect=AssertionError('No per-row widgets')):
                catalog.filter_library()
            self.assertEqual(len(catalog.library_folder_list.data), 1001)
            self.assertEqual(list(catalog.library_rows.children), [catalog.library_folder_list])
            stale = catalog.library_row_buttons[-1].on_press
            catalog.clear_private_libraries()
            self.assertEqual(len(catalog.library_folder_list.data), 1000)
            self.assertFalse(any(row.title == 'SESSION-ONLY-SECRET' for row in catalog.library_folder_list.data))
            with patch.object(app, 'show_files', side_effect=AssertionError('Retired private callback')):
                await stale()
        app.loop.run_until_complete(exercise())
