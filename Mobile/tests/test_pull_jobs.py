"""One-way refresh, local conflicts, interrupted publication and privacy."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from logisticsmobile.pull_jobs import PullJobs, folder_state
from commonUtils.persistence.publication import rename_exclusive


class Client:
    generation = 1
    identity = 'a' * 64
    data = b'first snapshot'
    def connection_identity(self, remote):
        return self.identity
    def entries(self, remote, path):
        return [dict(path='folder/note.txt', directory=False)]
    def download_into(self, remote, path, descriptor):
        os.write(descriptor, self.data)
    download_decrypted_into = download_into


class PullJobTests(unittest.TestCase):
    def test_refresh_retains_previous_copy_and_local_conflict_creates_separate_snapshot(self):
        with TemporaryDirectory() as directory:
            store = PullJobs(Path(directory))
            client = Client()
            job = store.create(client, 'remote', 'folder')
            target = store.local / job['target']
            client.data = b'remote update'
            self.assertEqual(store.run(job['id'], client), ('updated', target))
            self.assertEqual((target / 'note.txt').read_bytes(), client.data)
            backup = next(store.local.glob('*-previous-*'))
            self.assertEqual((backup / 'note.txt').read_bytes(), b'first snapshot')
            (target / 'note.txt').write_bytes(b'local edits')
            client.data = b'another remote update'
            status, incoming = store.run(job['id'], client)
            self.assertEqual(status, 'conflict')
            self.assertEqual((target / 'note.txt').read_bytes(), b'local edits')
            self.assertEqual((incoming / 'note.txt').read_bytes(), client.data)
            restored = PullJobs(Path(directory))
            self.assertEqual(restored.jobs[job['id']]['baseline'], job['baseline'])
            restored.remove(job['id'])
            self.assertTrue(target.exists())
            self.assertTrue(backup.exists())

    def test_changed_connection_and_cancellation_never_replace_local_target(self):
        with TemporaryDirectory() as directory:
            store, client = PullJobs(Path(directory)), Client()
            job = store.create(client, 'remote', 'folder')
            baseline = folder_state(store.local / job['target'])
            client.identity = 'b' * 64
            with self.assertRaisesRegex(ValueError, 'connection changed'):
                store.run(job['id'], client)
            client.identity = 'a' * 64
            with self.assertRaises(ValueError):
                store.run(job['id'], client, cancelled=lambda: True)
            self.assertEqual(folder_state(store.local / job['target']), baseline)

    def test_restart_reconciles_publication_after_metadata_write_failure(self):
        with TemporaryDirectory() as directory:
            store, client = PullJobs(Path(directory)), Client()
            job = store.create(client, 'remote', 'folder')
            client.data = b'updated'
            original = store.save
            count = [0]
            def fail_after_publish():
                count[0] += 1
                if count[0] == 2:
                    raise OSError('metadata failure after publication')
                return original()
            with patch.object(store, 'save', fail_after_publish):
                with self.assertRaises(OSError):
                    store.run(job['id'], client)
            restored = PullJobs(Path(directory))
            self.assertIsNotNone(restored.pending)
            restored.reconcile()
            self.assertIsNone(restored.pending)
            self.assertEqual(folder_state(restored.local / job['target']), restored.jobs[job['id']]['baseline'])
            self.assertEqual((restored.local / job['target'] / 'note.txt').read_bytes(), b'updated')

    def test_failed_rename_rolls_back_and_preserves_incoming_snapshot(self):
        with TemporaryDirectory() as directory:
            store, client = PullJobs(Path(directory)), Client()
            job = store.create(client, 'remote', 'folder')
            target = store.local / job['target']
            client.data = b'updated'
            count = [0]
            def fail_publication(source, destination):
                count[0] += 1
                if count[0] == 2:
                    raise OSError('publication failed')
                return rename_exclusive(source, destination)
            with patch('logisticsmobile.pull_jobs.rename_exclusive', fail_publication):
                with self.assertRaises(OSError):
                    store.run(job['id'], client)
            self.assertEqual((target / 'note.txt').read_bytes(), b'first snapshot')
            restored = PullJobs(Path(directory))
            restored.reconcile()
            self.assertTrue(any((path / 'note.txt').read_bytes() == b'updated' for path in store.local.iterdir()))

    def test_private_jobs_and_malformed_records_never_publish_private_recovery(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = PullJobs(root)
            job = store.create(Client(), 'secret remote', 'folder', decrypted=True)
            raw = store.path.read_text()
            self.assertNotIn('secret remote', raw)
            self.assertNotIn('note.txt', raw)
            self.assertNotIn(job['target'], raw)
            self.assertEqual(PullJobs(root).jobs, {})
            store.forget_private()
            self.assertEqual(store.jobs, {})
            store.path.write_text('malformed record')
            broken = PullJobs(root)
            self.assertTrue(broken.error)
            with self.assertRaises(ValueError):
                broken.save()
            self.assertEqual(store.path.read_text(), 'malformed record')
