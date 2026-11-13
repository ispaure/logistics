"""Shared runner failures leave provider search available and receipts diagnostic."""
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from time import monotonic
import unittest
from unittest.mock import patch

from commonUtils.filesystem.index import DirectoryCache
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.search.indexed import IndexedLocalSearch
from commonUtils.testing.stages import TestStage
from services.directory_index import acquire, cache_for

TEST_STAGE = TestStage.REGRESSION


class DirectoryIndexFailureTests(unittest.TestCase):
    def test_failed_shared_preparation_falls_back_and_keeps_the_failed_receipt(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / 'files'
            root.mkdir()
            (root / 'note.txt').write_text('note')
            database = base / 'cache' / 'index.sqlite3'
            lease = acquire(database)
            coordinator = lease.runner.coordinator
            submitted, receipts = coordinator.submit, []
            def submit(*args, **kwargs):
                identity = submitted(*args, **kwargs)
                receipts.append(identity)
                return identity
            try:
                with cache_for(database) as cache, \
                     patch.object(coordinator, 'submit', side_effect=submit), \
                     patch.object(DirectoryCache, 'get', side_effect=sqlite3.DatabaseError('Synthetic corrupt writer')):
                    search = IndexedLocalSearch(database, eligible=lambda provider: True, cache=cache)
                    deadline = monotonic() + 5
                    result = search.search(LocalFiles(root), '', 'note', cancelled=lambda: monotonic() >= deadline)
                self.assertEqual([row['path'] for row in result.rows], ['note.txt'])
                self.assertTrue(result.complete)
                self.assertEqual(len(receipts), 1)
                failed = coordinator.status(receipts[0])
                self.assertEqual(failed['state'], 'error')
                self.assertEqual(failed['error'], 'Synthetic corrupt writer')
                self.assertIsNone(coordinator.error)
            finally:
                lease.close()
                if lease.runner.worker.ident is not None:
                    lease.runner.worker.join(5)
                self.assertFalse(lease.runner.worker.is_alive())
