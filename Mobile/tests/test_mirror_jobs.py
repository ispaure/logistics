"""Publication recovery, push conflicts and ciphertext-only mapping records."""
from hashlib import sha256
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from logisticsmobile.mirror_jobs import MirrorJobs


class MirrorClient:
    generation = 1
    identity = 'a' * 64

    def __init__(self):
        self.data = {'folder/note.txt': b'first', 'encoded/opaque-name': b'ciphertext'}
        self.backups = []

    def connection_identity(self, remote):
        return self.identity

    def request(self, action, **values):
        path = values.get('path', '')
        if action == 'mirror_info':
            crypt = values['remote'] == 'Secret'
            return dict(identity=self.identity, crypt=crypt, cipher_identity='b' * 64 if crypt else '',
                        prefix='encoded' if crypt else path)
        if action == 'mirror_list':
            return [dict(path=key, directory=False, size=len(data)) for key, data in self.data.items()
                    if key.rpartition('/')[0] == path]
        if action == 'mirror_read':
            os.write(values['fd'], self.data[path])
            return len(self.data[path])
        if action == 'mirror_stat':
            return sha256(self.data[path]).hexdigest() if path in self.data else ''
        if action == 'mirror_mkdir':
            return True
        if action == 'mirror_validate':
            hash = sha256()
            while block := os.read(values['fd'], 65536):
                hash.update(block)
            return hash.hexdigest()
        if action == 'mirror_write':
            current = self.request('mirror_stat', path=path)
            if current != values['expected']:
                raise ValueError('Remote changed')
            if path in self.data:
                self.backups.append(self.data[path])
            data = b''
            while block := os.read(values['fd'], 65536):
                data += block
            self.data[path] = data
            return sha256(data).hexdigest()
        raise ValueError(action)


class MirrorJobTests(unittest.TestCase):
    def test_local_edit_conflict_snapshot_push_backup_and_remote_conflict(self):
        with TemporaryDirectory() as directory:
            store, client = MirrorJobs(directory), MirrorClient()
            job, result = store.create(client, 'Remote', 'folder')
            self.assertEqual(result, ('updated', None))
            target = store.target(job) / 'note.txt'
            target.write_bytes(b'local edit')
            status, snapshot = store.pull(job['id'], client)
            self.assertEqual(status, 'conflict')
            self.assertEqual(target.read_bytes(), b'local edit')
            self.assertEqual((store.snapshot(job, snapshot) / 'note.txt').read_bytes(), b'first')
            plan = store.push_plan(job['id'], client)
            self.assertEqual(store.push(plan, client), 1)
            self.assertEqual(client.data['folder/note.txt'], b'local edit')
            self.assertEqual(client.backups, [b'first'])
            self.assertEqual(store.push_plan(job['id'], client)['writes'], [])
            client.data['folder/note.txt'] = b'external remote edit'
            target.write_bytes(b'another local edit')
            with self.assertRaisesRegex(ValueError, 'remote file changed'):
                store.push_plan(job['id'], client)
            self.assertEqual(client.data['folder/note.txt'], b'external remote edit')

    def test_crypt_records_contain_only_raw_names_and_ciphertext(self):
        with TemporaryDirectory() as directory:
            store, client = MirrorJobs(directory), MirrorClient()
            job, result = store.create(client, 'Secret', 'private folder title')
            self.assertEqual(result, ('updated', None))
            self.assertEqual((store.target(job) / 'opaque-name').read_bytes(), b'ciphertext')
            self.assertNotIn(b'private folder title', store.path.read_bytes())
            self.assertNotIn(b'ciphertext', store.path.read_bytes())
            restored = MirrorJobs(directory)
            self.assertEqual(restored.jobs[job['id']]['prefix'], 'encoded')
            restored.remove(job['id'])
            self.assertTrue(store.target(job).exists())

    def test_changed_connection_and_reviewed_local_changes_never_upload(self):
        with TemporaryDirectory() as directory:
            store, client = MirrorJobs(directory), MirrorClient()
            job, _ = store.create(client, 'Remote', 'folder')
            target = store.target(job) / 'note.txt'
            target.write_bytes(b'local edit')
            plan = store.push_plan(job['id'], client)
            target.write_bytes(b'changed after review')
            with self.assertRaisesRegex(ValueError, 'changed since review'):
                store.push(plan, client)
            client.identity = 'c' * 64
            with self.assertRaisesRegex(ValueError, 'connection changed'):
                store.pull(job['id'], client)
            self.assertEqual(client.data['folder/note.txt'], b'first')
            self.assertEqual(target.read_bytes(), b'changed after review')

    def test_interrupted_publication_restores_prior_copy_and_keeps_incoming(self):
        with TemporaryDirectory() as directory:
            store, client = MirrorJobs(directory), MirrorClient()
            job, _ = store.create(client, 'Remote', 'folder')
            client.data['folder/note.txt'] = b'new remote'
            from commonUtils.persistence.publication import rename_exclusive
            calls = []
            def fail_second(source, destination):
                calls.append(source)
                if len(calls) == 2:
                    raise OSError('Interrupted publication')
                rename_exclusive(source, destination)
            with patch('logisticsmobile.mirror_jobs.rename_exclusive', side_effect=fail_second):
                with self.assertRaises(OSError):
                    store.pull(job['id'], client)
            restored = MirrorJobs(directory)
            self.assertIsNotNone(restored.pending)
            restored.reconcile()
            self.assertEqual((restored.target(job) / 'note.txt').read_bytes(), b'first')
            self.assertTrue(any((restored.snapshot(job, key) / 'note.txt').read_bytes() == b'new remote'
                                for key in restored.jobs[job['id']]['snapshots']))

    def test_cancelled_pull_never_publishes_partial_tree_and_symlinks_refuse_push(self):
        with TemporaryDirectory() as directory:
            store, client = MirrorJobs(directory), MirrorClient()
            job, _ = store.create(client, 'Remote', 'folder')
            stopped = []
            def progress(**values):
                if values['files']:
                    stopped.append(True)
            with self.assertRaisesRegex(ValueError, 'cancelled'):
                store.pull(job['id'], client, cancelled=lambda: bool(stopped), progress=progress)
            self.assertEqual((store.target(job) / 'note.txt').read_bytes(), b'first')
            (store.target(job) / 'linked').symlink_to('/private/tmp')
            with self.assertRaisesRegex(ValueError, 'Linked'):
                store.push_plan(job['id'], client)

    def test_malformed_manifest_is_preserved(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'mirror-jobs.json'
            path.write_bytes(b'{ broken')
            store = MirrorJobs(directory)
            self.assertTrue(store.error)
            with self.assertRaises(ValueError):
                store.create(MirrorClient(), 'Remote', 'folder')
            self.assertEqual(path.read_bytes(), b'{ broken')
