"""Library record caches invalidate on source revisions and expose copies only."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from logisticsmobile.library import LibraryStore


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

    def test_warm_scan_reuses_validation_and_returned_records_are_isolated(self):
        self.store.items()
        with patch.object(self.store, 'decode_record', side_effect=AssertionError('Unchanged record')):
            records, warnings = self.store.items()
        self.assertFalse(warnings)
        records[0]['bookmarks'].append(3)
        self.assertEqual(self.store.cached_items()[0][0]['bookmarks'], [])

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
