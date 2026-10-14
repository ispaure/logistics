"""Publication recovery, push conflicts and ciphertext-only mapping records."""
from hashlib import sha256
import os
import json
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
        self.directories = set()

    def connection_identity(self, remote):
        return self.identity

    def request(self, action, **values):
        path = values.get('path', '')
        if action == 'mirror_progress':
            return dict(phase='Transferring', done=5, total=10, files=1, total_files=2,
                        listed=3, checks=1, active=1)
        if action == 'mirror_info':
            crypt = values['remote'] == 'Secret' and not values.get('decrypted')
            return dict(identity=self.identity, crypt=crypt, cipher_identity='b' * 64 if crypt else '',
                        prefix='encoded' if crypt else path)
        if action == 'mirror_list':
            folders = set(self.directories)
            for key in self.data:
                parts = key.split('/')
                folders.update('/'.join(parts[:i]) for i in range(1, len(parts)))
            return ([dict(path=key, directory=False, size=len(data)) for key, data in self.data.items()
                     if key.rpartition('/')[0] == path] +
                    [dict(path=key, directory=True, size=0) for key in sorted(folders) if key.rpartition('/')[0] == path])
        if action == 'mirror_sync':
            import shutil
            target = Path(values['local_path'])
            prefix = path + '/' if path else ''
            if values['push']:
                local = {child.relative_to(target).as_posix(): child.read_bytes() for child in target.rglob('*') if child.is_file()}
                transferred = sum(self.data.get(prefix + key) != data for key, data in local.items())
                self.data = {key: data for key, data in self.data.items() if not key.startswith(prefix)}
                self.data.update({prefix + key: data for key, data in local.items()})
                self.directories = {key for key in self.directories if not key.startswith(prefix)}
                self.directories.update(prefix + child.relative_to(target).as_posix() for child in target.rglob('*') if child.is_dir())
                return transferred
            for child in list(target.iterdir()):
                shutil.rmtree(child) if child.is_dir() else child.unlink()
            for key, data in self.data.items():
                if key.startswith(prefix):
                    destination = target / key[len(prefix):]
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with destination.open('wb') as stream:
                        self.request('mirror_read', path=key, fd=stream.fileno())
            for key in self.directories:
                if key.startswith(prefix):
                    (target / key[len(prefix):]).mkdir(parents=True, exist_ok=True)
            return 1
        if action == 'mirror_read':
            os.write(values['fd'], self.data[path])
            return len(self.data[path])
        if action == 'mirror_stat':
            return sha256(self.data[path]).hexdigest() if path in self.data else ''
        if action == 'mirror_mkdir':
            self.directories.add(path)
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
    def test_legacy_crypto_tree_is_preserved_and_requires_a_new_scoped_pull(self):
        with TemporaryDirectory() as directory:
            store, client = MirrorJobs(directory), MirrorClient()
            job, _ = store.create(client, 'Secret', 'private folder title')
            legacy = store.root / 'LocalCryptFolders' / job['cipher_identity'] / job['prefix']
            legacy.parent.mkdir(parents=True)
            store.target(job).rename(legacy)
            (legacy / 'opaque-name').write_bytes(b'legacy local edits')
            value = json.loads(store.path.read_bytes())
            value['schema'] = 1
            value['pending'] = None
            value['jobs'][0]['snapshots'] = []
            store.path.write_text(json.dumps(value))
            restored = MirrorJobs(directory)
            with self.assertRaisesRegex(ValueError, 'Pull this folder'):
                restored.push_plan(job['id'], client)
            self.assertEqual(restored.pull(job['id'], client), ('updated', None))
            self.assertEqual((legacy / 'opaque-name').read_bytes(), b'legacy local edits')
            self.assertEqual((restored.target(job) / 'opaque-name').read_bytes(), b'ciphertext')

    def test_empty_subfolder_push_and_stable_source_snapshot(self):
        with TemporaryDirectory() as directory:
            store, client = MirrorJobs(directory), MirrorClient()
            job, _ = store.create(client, 'Remote', 'folder')
            (store.target(job) / 'empty').mkdir()
            plan = store.push_plan(job['id'], client)
            self.assertEqual(plan['directories'], ['empty'])
            self.assertEqual(store.push(plan, client), 0)
            self.assertIsNone(store.jobs[job['id']]['baseline']['empty'])

    def test_crypto_accounts_cannot_claim_the_same_local_remote_name(self):
        with TemporaryDirectory() as directory:
            store, client = MirrorJobs(directory), MirrorClient()
            first, _ = store.create(client, 'Secret', 'private folder title')
            first_file = store.target(first) / 'opaque-name'
            first_file.write_bytes(b'first account local edits')
            client.identity = 'c' * 64
            client.data['encoded/opaque-name'] = b'second account ciphertext'
            with self.assertRaisesRegex(ValueError, 'belongs to another copy'):
                store.create(client, 'Secret', 'private folder title')
            self.assertEqual(len(store.jobs), 1)
            self.assertEqual(first_file.read_bytes(), b'first account local edits')

    def test_new_local_copy_keeps_exact_remote_name_and_existing_names_stay_readable(self):
        with TemporaryDirectory() as directory:
            store, client = MirrorJobs(directory), MirrorClient()
            job, _ = store.create(client, 'Example-LIb-Books', storage='Local')
            self.assertEqual(job['target'], 'Example-LIb-Books')
            self.assertEqual(store.target(job).name, 'Example-LIb-Books')
            old = store.target(job)
            job['target'] += '-' + job['id'][:8]
            old.rename(store.target(job))
            store.save()
            restored = MirrorJobs(directory)
            same, _ = restored.create(client, 'Example-LIb-Books', storage='Local')
            self.assertEqual(same['id'], job['id'])
            self.assertEqual(same['target'], 'Example-LIb-Books')
            self.assertTrue(restored.target(same).is_dir())

    def test_unmapped_or_case_conflicting_folder_is_preserved(self):
        with TemporaryDirectory() as directory:
            store, client = MirrorJobs(directory), MirrorClient()
            target = Path(directory) / 'LocalFiles' / 'remote'
            target.mkdir(parents=True)
            (target / 'keep.txt').write_text('local edit')
            with self.assertRaisesRegex(ValueError, 'already exists'):
                store.create(client, 'Remote', storage='Local')
            self.assertEqual((target / 'keep.txt').read_text(), 'local edit')

    def test_legacy_name_migration_rolls_back_failed_save_and_refuses_collision(self):
        with TemporaryDirectory() as directory:
            store, client = MirrorJobs(directory), MirrorClient()
            job, _ = store.create(client, 'Remote', 'folder', storage='Local')
            original = store.target(job)
            job['target'] += '-' + job['id'][:8]
            legacy = store.target(job)
            original.rename(legacy)
            store.save()
            with patch.object(store, 'save', side_effect=OSError('write failed')):
                with self.assertRaisesRegex(OSError, 'write failed'):
                    store.update_legacy_name(job, 'folder')
            self.assertEqual(store.target(job), legacy)
            self.assertEqual((legacy / 'note.txt').read_bytes(), b'first')
            self.assertFalse(original.exists())
            original.mkdir()
            (original / 'keep.txt').write_text('keep')
            with self.assertRaisesRegex(ValueError, 'already exists'):
                store.pull(job['id'], client)
            self.assertEqual((original / 'keep.txt').read_text(), 'keep')
            self.assertEqual((legacy / 'note.txt').read_bytes(), b'first')

    def test_sync_forwards_real_counters_and_final_snapshot(self):
        from threading import Event
        with TemporaryDirectory() as directory:
            store, client = MirrorJobs(directory), MirrorClient()
            job, _ = store.create(client, 'Remote', 'folder')
            received = Event()
            updates = []
            def report(**values):
                updates.append(values)
                if values.get('active'):
                    received.set()
            original = client.request
            def slow(action, **values):
                if action == 'mirror_sync':
                    if not received.wait(3):
                        raise AssertionError('No live progress received')
                return original(action, **values)
            client.request = slow
            store.pull(job['id'], client, progress=report)
            live = next(value for value in updates if value.get('active'))
            self.assertEqual((live['files'], live['total_files'], live['done'], live['total']), (1, 2, 5, 10))
            self.assertEqual((live['listed'], live['checks']), (3, 1))
            self.assertEqual(updates[-1]['files'], 1)

    def test_external_record_edits_refuse_push_without_replacing_metadata(self):
        with TemporaryDirectory() as directory:
            store, client = MirrorJobs(directory), MirrorClient()
            job, _ = store.create(client, 'Remote', 'folder')
            (store.target(job) / 'note.txt').write_bytes(b'local edit')
            plan = store.push_plan(job['id'], client)
            external = store.path.read_bytes() + b'\n'
            store.path.write_bytes(external)
            with self.assertRaisesRegex(OSError, 'records changed'):
                store.push(plan, client)
            self.assertEqual(store.path.read_bytes(), external)
            self.assertEqual(client.data['folder/note.txt'], b'first')

    def test_plain_sync_removes_destination_only_files_and_requires_fresh_review(self):
        with TemporaryDirectory() as directory:
            store, client = MirrorJobs(directory), MirrorClient()
            job, _ = store.create(client, 'Remote', 'folder')
            target = store.target(job)
            (target / 'local-only.txt').write_bytes(b'local only')
            (target / 'note.txt').write_bytes(b'local edit')
            store.pull(job['id'], client)
            self.assertFalse((target / 'local-only.txt').exists())
            self.assertEqual((target / 'note.txt').read_bytes(), b'first')
            self.assertNotIn('snapshots', job)
            (target / 'note.txt').unlink()
            (target / 'added.txt').write_bytes(b'added')
            client.data['folder/nested/removed.txt'] = b'remove me'
            client.data['elsewhere/keep.txt'] = b'outside selected folder'
            plan = store.push_plan(job['id'], client)
            self.assertIn('nested/removed.txt', plan['deletes'])
            self.assertIn('note.txt', plan['deletes'])
            self.assertEqual(store.push(plan, client), 1)
            self.assertEqual({key for key in client.data if key.startswith('folder/')}, {'folder/added.txt'})
            self.assertEqual(client.data['elsewhere/keep.txt'], b'outside selected folder')
            self.assertEqual(client.backups, [])
            plan = store.push_plan(job['id'], client)
            client.data['folder/new-after-review.txt'] = b'new'
            with self.assertRaisesRegex(ValueError, 'Remote files changed since review'):
                store.push(plan, client)
            self.assertIn('folder/new-after-review.txt', client.data)

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

    def test_failed_sync_keeps_destination_mapping_for_retry_and_symlinks_refuse_push(self):
        with TemporaryDirectory() as directory:
            store, client = MirrorJobs(directory), MirrorClient()
            job, _ = store.create(client, 'Remote', 'folder')
            original = client.request
            def fail(action, **values):
                if action == 'mirror_sync':
                    (store.target(job) / 'partial.txt').write_bytes(b'completed before failure')
                    raise ValueError('sync cancelled')
                return original(action, **values)
            with patch.object(client, 'request', side_effect=fail):
                with self.assertRaisesRegex(ValueError, 'cancelled'):
                    store.pull(job['id'], client)
            restored = MirrorJobs(directory)
            self.assertIn(job['id'], restored.jobs)
            self.assertEqual((store.target(job) / 'partial.txt').read_bytes(), b'completed before failure')
            self.assertNotIn('snapshots', job)
            (store.target(job) / 'linked').symlink_to('/private/tmp')
            with self.assertRaisesRegex(ValueError, 'Linked'):
                store.push_plan(job['id'], client)

    def test_confirmed_wipe_removes_both_storage_types_without_inventory_or_following_links(self):
        for remote in ('Remote', 'Secret'):
            with self.subTest(remote=remote), TemporaryDirectory() as directory, TemporaryDirectory() as outside:
                store, client = MirrorJobs(directory), MirrorClient()
                job, _ = store.create(client, remote, 'folder')
                target = store.target(job)
                keep = Path(outside) / 'keep.txt'
                keep.write_text('outside storage')
                (target / 'linked').symlink_to(outside, target_is_directory=True)
                (target / 'added-after-confirmation').write_text('also delete')
                sibling = target.parent / 'sibling'
                sibling.mkdir()
                with (patch.object(store, 'state', side_effect=AssertionError('No content scan')),
                      patch('commonUtils.runtime.resource_mutations.inventory', side_effect=AssertionError('No inventory'))):
                    store.delete_copy(job['id'])
                self.assertFalse(target.exists())
                self.assertTrue(sibling.exists())
                self.assertEqual(keep.read_text(), 'outside storage')
                self.assertNotIn(job['id'], MirrorJobs(directory).jobs)
                self.assertEqual(client.data['folder/note.txt'], b'first')

    def test_legacy_snapshots_and_pending_restore_are_discarded_when_wiping(self):
        with TemporaryDirectory() as directory:
            store, client = MirrorJobs(directory), MirrorClient()
            job, _ = store.create(client, 'Remote', 'folder')
            backup, incoming = 'c' * 32, 'd' * 32
            for key in (backup, incoming):
                tree = store.root / 'TransferSnapshots' / key / 'tree'
                tree.mkdir(parents=True)
                (tree / 'note.txt').write_bytes(b'old recovery copy')
            records = json.loads(store.path.read_bytes())
            records['schema'] = 2
            records['jobs'][0]['snapshots'] = [backup]
            records['pending'] = dict(job=job['id'], backup=backup, incoming=incoming, baseline=job['baseline'])
            store.path.write_text(json.dumps(records))
            restored = MirrorJobs(directory)
            self.assertFalse(restored.error)
            self.assertNotIn('snapshots', restored.jobs[job['id']])
            with patch.object(restored, 'state', side_effect=AssertionError('No restore or inventory')):
                restored.delete_copy(job['id'])
            self.assertFalse((store.root / 'TransferSnapshots').exists())
            restarted = MirrorJobs(directory)
            restarted.reconcile()
            self.assertFalse(store.target(job).exists())
            self.assertEqual(restarted.jobs, {})
            self.assertEqual(json.loads(store.path.read_bytes())['schema'], 3)
            self.assertNotIn('pending', json.loads(store.path.read_bytes()))

    def test_wipe_rejects_roots_parent_traversal_and_linked_targets(self):
        with TemporaryDirectory() as directory:
            store = MirrorJobs(directory)
            local = store.root / 'LocalFiles'
            local.mkdir()
            target = local / 'linked'
            target.symlink_to(store.root, target_is_directory=True)
            for path in (store.root, local, store.root / 'LocalCryptFolders',
                         local / '..' / 'mirror-jobs.json', target):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    store.wipe_folder(path)
            self.assertTrue(local.exists())

    def test_malformed_manifest_is_preserved(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'mirror-jobs.json'
            path.write_bytes(b'{ broken')
            store = MirrorJobs(directory)
            self.assertTrue(store.error)
            with self.assertRaises(ValueError):
                store.create(MirrorClient(), 'Remote', 'folder')
            self.assertEqual(path.read_bytes(), b'{ broken')


class MirrorProgressDisplayTests(unittest.TestCase):
    def test_discovery_does_not_restart_animation_and_transfer_shows_real_work(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from logisticsmobile.mirror_ui import MirrorUI
        bar = SimpleNamespace(max=None, value=0, start=Mock(), stop=Mock())
        origin = SimpleNamespace(max=None, value=0, start=Mock(), stop=Mock())
        app = SimpleNamespace(active_host=True, transfer_epoch=1, transfer_busy=True,
                              transfer_progress=bar, cloud_transfer_progress=origin,
                              refresh_transfer_status=Mock(),
                              transfer_notice=SimpleNamespace(text=''), cloud_status=SimpleNamespace(value=''))
        discovering = dict(phase='Discovering / checking files', files=0, done=0, total=0,
                           listed=24, checks=8)
        for _ in range(3):
            MirrorUI.publish_mirror_progress(app, 1, discovering)
        bar.start.assert_not_called()
        origin.start.assert_not_called()
        self.assertIn('24 discovered', app.transfer_message)
        live = dict(phase='Transferring', files=2, total_files=4, done=50, total=100, active=1)
        for _ in range(3):
            MirrorUI.publish_mirror_progress(app, 1, live)
        bar.stop.assert_called_once()
        origin.stop.assert_called_once()
        self.assertEqual(bar.value, 50)
        self.assertIn('2 file(s) completed / 4 known', app.transfer_message)
        self.assertIn('1 transferring', app.transfer_message)
        self.assertIn('50 / 100 bytes', app.transfer_message)
        MirrorUI.publish_mirror_progress(app, 1, dict(phase='Transferring', files=0, done=32, total=0))
        self.assertIn('32 bytes transferred', app.transfer_message)
        bar.start.assert_called_once()
        MirrorUI.publish_mirror_progress(app, 0, live)
        self.assertIsNone(bar.max)
