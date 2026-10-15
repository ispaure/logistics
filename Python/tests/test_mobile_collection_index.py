"""Large-library indexing, resumable work, Unicode matching and privacy boundaries."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from features.comics.mobile.index import CollectionIndex


class CollectionIndexTests(unittest.TestCase):
    def test_superseded_worker_does_not_prune_newer_completed_index(self):
        from threading import Event, Thread
        with TemporaryDirectory() as directory:
            index = CollectionIndex(Path(directory) / 'metadata.sqlite3')
            rows = [dict(id=str(i), name=f'{i}.cbz', digest=str(i)) for i in range(2)]
            started, retired = Event(), Event()
            def stale():
                started.set()
                index.scan(rows[:1], signature=lambda r: 1, load=lambda r: {}, cancelled=retired.is_set)
            with index.lock:
                worker = Thread(target=stale)
                worker.start()
                self.assertTrue(started.wait(5))
                index.scan(rows, signature=lambda r: 1, load=lambda r: {'Writer': 'Current'})
                retired.set()
            worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(index.page('Current')[1], 2)

    def test_corrupt_disposable_index_rebuilds_and_bad_archive_does_not_stop_scan(self):
        from zipfile import BadZipFile
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'metadata.sqlite3'
            path.write_bytes(b'not a database')
            index = CollectionIndex(path)
            rows = [dict(id=str(i), name=f'{i}.cbz', digest=str(i)) for i in range(2)]
            def load(record):
                if record['id'] == '0':
                    raise BadZipFile('Synthetic broken archive')
                return {'Writer': 'Valid writer'}
            index.scan(rows, signature=lambda r: 1, load=load)
            self.assertEqual(index.page('Valid writer')[0], ['1'])
            self.assertEqual(index.page('0.cbz')[0], ['0'])

    def test_large_incremental_index_pages_unicode_and_changed_deleted_entries(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'metadata.sqlite3'
            index = CollectionIndex(path)
            records = [dict(id=str(i), name=f'Comic {i:05}.cbz', digest=str(i)) for i in range(5001)]
            records[-1]['name'] = 'Straße.cbz'
            signatures = {r['id']: 1 for r in records}
            opened = []
            def load(record):
                opened.append(record['id'])
                return {'Writer': 'Beyond the old cap' if record['id'] == '5000' else 'Alice'}
            def scan(rows):
                index.scan(rows, signature=lambda r: signatures[r['id']], load=load)
            scan(records)
            self.assertEqual(len(opened), 5001)
            keys, total = index.page('', offset=5000)
            self.assertEqual((keys, total), (['5000'], 5001))
            self.assertEqual(index.page('STRASSE beyond')[0], ['5000'])
            index = CollectionIndex(path)  # Persistent across app launches.
            opened.clear()
            scan(records)
            self.assertEqual(opened, [])
            signatures['5000'] = 2
            records[-1]['digest'] = 'new'
            scan(records[:-2] + records[-1:])
            self.assertEqual(opened, ['5000'])
            self.assertEqual(index.page('')[1], 5000)
            self.assertNotIn('4999', index.page('Comic 04999')[0])

    def test_cancelled_partial_index_resumes_and_protected_metadata_is_excluded(self):
        with TemporaryDirectory() as directory:
            index = CollectionIndex(Path(directory) / 'metadata.sqlite3')
            rows = [dict(id=str(i), name=f'{i}.cbz', digest=str(i)) for i in range(301)]
            stopped, reads = False, []
            def load(record):
                nonlocal stopped
                reads.append(record['id'])
                if len(reads) == 30:
                    stopped = True
                return None if record['id'] == '0' else {'Title': 'Indexed title', 'Writer': 'Indexed writer'}
            index.scan(rows, signature=lambda r: 1, load=load, cancelled=lambda: stopped)
            self.assertLess(len(reads), 301)
            stopped = False
            index.scan(rows, signature=lambda r: 1, load=lambda r: None if r['id'] == '0' else {'Title': 'Indexed title', 'Writer': 'Indexed writer'})
            self.assertEqual(index.page('Indexed title')[1], 300)
            self.assertEqual(index.page('0.cbz')[0][0], '0')
            self.assertNotIn('0', index.page('Indexed title', limit=400)[0])
            self.assertEqual(index.suggestions()['Writer'], ['Indexed writer'])
