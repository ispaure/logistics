"""Host-owned scheduling, scene leases and shared filename admission."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import unittest
from unittest.mock import patch

from commonUtils.filesystem.index import DirectoryCache
from commonUtils.runtime.operations import OperationCancelled
from services.directory_index import ScanPolicy, acquire, cache_for, coordinator_for, foreground


class DirectoryIndexPolicyTests(unittest.TestCase):
    def test_foreground_debounce_yield_and_background_turn(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = DirectoryCache(database=root / 'index.sqlite3')
            policy = ScanPolicy(cache)
            jobs = [dict(id='background', root=str(root/'background')), dict(id='notes', root=str(root/'notes'))]
            policy.coordinator = type('Queue', (), {'active_jobs': lambda self: jobs})()
            with patch('services.directory_index.monotonic', return_value=0):
                self.assertEqual(policy.select_job(jobs)['id'], 'background')
                policy.focus('visible', [root/'notes'/'child'])
            with patch('services.directory_index.monotonic', return_value=.1):
                self.assertEqual(policy._choose(jobs)['id'], 'background')
                self.assertFalse(policy.should_yield(jobs[0]))
            with patch('services.directory_index.monotonic', return_value=.6):
                self.assertTrue(policy.should_yield(jobs[0]))
                self.assertEqual(policy.select_job(jobs)['id'], 'notes')
            with patch('services.directory_index.monotonic', return_value=5.1):
                self.assertTrue(policy.should_yield(jobs[1]))
                self.assertEqual(policy.select_job(jobs)['id'], 'background')
            with patch('services.directory_index.monotonic', return_value=5.7):
                self.assertFalse(policy.should_yield(jobs[0]))
            with patch('services.directory_index.monotonic', return_value=6.2):
                self.assertTrue(policy.should_yield(jobs[0]))
            # A repeatedly resumed atomic refresh eventually gets enough time
            # to commit even while another workspace keeps foreground demand.
            with patch('services.directory_index.monotonic', return_value=10.7):
                self.assertEqual(policy.select_job(jobs)['id'], 'notes')
            with patch('services.directory_index.monotonic', return_value=11.8):
                self.assertTrue(policy.should_yield(jobs[1]))
                self.assertEqual(policy.select_job(jobs)['id'], 'background')
            with patch('services.directory_index.monotonic', return_value=13):
                self.assertFalse(policy.should_yield(jobs[0]))
            policy.active('scene', False)
            self.assertTrue(policy.should_yield(jobs[0]))
            policy.retire('visible')
            self.assertFalse(cache._priority_folders)
            cache.close()

    def test_scene_leases_are_lazy_and_retire_only_the_last_host(self):
        with TemporaryDirectory() as temporary:
            database = Path(temporary)/'index.sqlite3'
            first, second = acquire(database), acquire(database)
            try:
                self.assertIs(first.runner, second.runner)
                self.assertFalse(first.runner.worker.is_alive())
                first.set_active(False)
                job = dict(id='pending', root=temporary)
                self.assertIsNotNone(first.runner.policy.select_job([job]))
                second.set_active(False)
                self.assertIsNone(first.runner.policy.select_job([job]))
                second.set_active(True)
                first.close()
                self.assertIs(coordinator_for(database), second.runner.coordinator)
                self.assertFalse(second.runner.stop.is_set())
            finally:
                first.close()
                second.close()
            self.assertTrue(second.runner.stop.is_set())
            self.assertIsNone(coordinator_for(database))

    def test_two_search_followers_share_traversal_and_cancel_independently(self):
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base/'tree'
            root.mkdir()
            (root/'one.txt').write_text('one')
            database = base/'cache'/'index.sqlite3'
            lease = acquire(database)
            entered, release, cancel = Event(), Event(), Event()
            enumeration = []
            original = DirectoryCache._scan_folder
            results, errors = [], []
            def scanned(cache, db, generation, scan_root, recursive, folder, cancelled, report, **kwargs):
                enumeration.append(folder)
                entered.set()
                if not release.wait(5):
                    raise TimeoutError('Synthetic traversal was not released')
                return original(cache, db, generation, scan_root, recursive, folder, cancelled, report, **kwargs)
            def prepare(stop):
                try:
                    with cache_for(database) as cache, foreground(database, root):
                        with cache.coordinator.prepare_search(root, cancelled=stop) as snapshot:
                            results.append(len(snapshot.entries))
                except OperationCancelled:
                    errors.append('cancelled')
            first = Thread(target=prepare, args=(cancel.is_set,))
            second = Thread(target=prepare, args=(lambda: False,))
            try:
                with patch.object(DirectoryCache, '_scan_folder', scanned):
                    first.start()
                    self.assertTrue(entered.wait(5))
                    second.start()
                    cancel.set()
                    first.join(5)
                    self.assertFalse(first.is_alive())
                    self.assertEqual(errors, ['cancelled'])
                    self.assertFalse(lease.runner.stop.is_set())
                    release.set()
                    second.join(5)
                    self.assertFalse(second.is_alive())
                self.assertEqual(results, [1])
                self.assertEqual(enumeration, [root])
            finally:
                cancel.set()
                release.set()
                first.join(5)
                if second.ident is not None:
                    second.join(5)
                lease.close()
                lease.runner.worker.join(5)
                self.assertFalse(lease.runner.worker.is_alive())
