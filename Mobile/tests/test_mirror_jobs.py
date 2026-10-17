"""Publication recovery, push conflicts and ciphertext-only mapping records."""
from hashlib import sha256
import os
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from features.rclone.transfers.mobile.jobs import MirrorJobs


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
        if action in ('mirror_review_progress', 'mirror_review_clear'):
            return dict(changes=[])
        if action == 'mirror_review':
            target = Path(values['local_path'])
            local = {p.relative_to(target).as_posix(): p.read_bytes().hex()
                     for p in target.rglob('*') if p.is_file()} if target.exists() else {}
            prefix = path + '/' if path else ''
            online = {key[len(prefix):]: value.hex() for key, value in self.data.items() if key.startswith(prefix)}
            source, destination = (local, online) if values['push'] else (online, local)
            changes = [[('add' if name not in destination else 'match' if source[name] == destination[name]
                        else 'replace'), name] for name in source]
            changes += [['delete', name] for name in destination if name not in source]
            fingerprint = sha256(json.dumps([source, destination], sort_keys=True).encode()).hexdigest()
            return dict(changes=changes, fingerprint=fingerprint)
        if action == 'crypt_path':
            return dict(path=path, identity='b' * 64)
        if action == 'mirror_info':
            crypt = values['remote'] == 'Secret' and not values.get('decrypted')
            return dict(identity=self.identity, crypt=crypt, cipher_identity='b' * 64 if crypt else '',
                        prefix='encoded' if crypt else path)
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
                        self.copy_remote_file(key, stream)
            for key in self.directories:
                if key.startswith(prefix):
                    (target / key[len(prefix):]).mkdir(parents=True, exist_ok=True)
            return 1
        if action == 'mirror_validate':
            hash = sha256()
            while block := os.read(values['fd'], 65536):
                hash.update(block)
            return hash.hexdigest()
        raise ValueError(action)

    def copy_remote_file(self, path, stream):
        stream.write(self.data[path])


class MirrorJobTests(unittest.TestCase):
    def test_inspect_large_copy_and_keep_link_and_cancellation_checks(self):
        with TemporaryDirectory() as directory:
            store = MirrorJobs(directory)
            local = store.root / 'LocalFiles' / 'Large'
            local.mkdir(parents=True)
            for index in range(10001):
                (local / f'{index:05}.txt').touch()
            for copy_links in (False, True):
                with self.subTest(copy_links=copy_links):
                    self.assertEqual(len(store.inspect(local, copy_links=copy_links)), 10001)
                    with self.assertRaisesRegex(ValueError, 'cancelled'):
                        store.inspect(local, lambda: True, copy_links=copy_links)
                    link = local / 'zz-linked-folder'
                    link.symlink_to(local, target_is_directory=True)
                    try:
                        with self.assertRaisesRegex(ValueError, 'Linked directories'):
                            store.inspect(local, copy_links=copy_links)
                    finally:
                        link.unlink()

    def test_inferred_push_uses_folder_name_and_specific_push_uses_remote_subfolder(self):
        with TemporaryDirectory() as directory:
            store, client = MirrorJobs(directory), MirrorClient()
            local = store.root / 'LocalFiles' / 'Books'
            local.mkdir(parents=True)
            (local / 'note.txt').write_bytes(b'new book')
            whole = store.prepare_push(client, 'Books')
            self.assertEqual((whole['remote'], whole['prefix'], whole['target']), ('Books', '', 'Books'))
            specific = store.prepare_push(client, 'Books', remote='Library', specific=True)
            self.assertEqual((specific['remote'], specific['prefix'], specific['target']), ('Library', 'Books', 'Books'))
            self.assertFalse(store.path.exists())
            store.execute_review(specific, client, new=True, push=True)
            self.assertEqual(client.data['Books/note.txt'], b'new book')
            with self.assertRaisesRegex(ValueError, 'belongs to another copy'):
                store.prepare_push(client, 'Books')

    def test_ordinary_file_link_is_followed_but_crypt_link_is_rejected(self):
        with TemporaryDirectory() as directory:
            store, client = MirrorJobs(directory), MirrorClient()
            job, _ = store.create(client, 'Remote', 'folder')
            source = store.root / 'outside.txt'
            source.write_bytes(b'linked file contents')
            (store.target(job) / 'link.txt').symlink_to(source)
            store.execute_push(job['id'], client)
            self.assertEqual(client.data['folder/link.txt'], source.read_bytes())
            with self.assertRaisesRegex(ValueError, 'links cannot be transferred'):
                store.inspect(store.target(job), copy_links=False)

    def test_push_cleans_only_allowlisted_junk_and_authenticates_encrypted_junk_first(self):
        with TemporaryDirectory() as directory:
            store, client = MirrorJobs(directory), MirrorClient()
            job, _ = store.create(client, 'Secret', 'private')
            root = store.target(job)
            junk = root / 'opaque-junk'
            junk.write_bytes(b'RCLONE\x00\x00' + b'synthetic ciphertext')
            plain = root / '.DS_Store'
            plain.write_bytes(b'generated plaintext')
            request = client.request
            def native(action, **values):
                if action == 'crypt_path':
                    return dict(path=values['path'].replace('opaque-junk', 'Thumbs.db'))
                if action == 'mirror_validate' and values['path'].endswith('opaque-junk'):
                    raise ValueError('ciphertext authentication failed')
                return request(action, **values)
            with patch.object(client, 'request', side_effect=native):
                with self.assertRaisesRegex(ValueError, 'authentication failed'):
                    store.execute_push(job['id'], client)
                junk.write_bytes(b'corrupted ciphertext header')
                with self.assertRaisesRegex(ValueError, 'authentication failed'):
                    store.execute_push(job['id'], client)
            self.assertTrue(junk.exists(), 'encrypted junk must authenticate before deletion')
            self.assertFalse(plain.exists())
            def valid(action, **values):
                if action == 'crypt_path':
                    return dict(path=values['path'].replace('opaque-junk', 'Thumbs.db'))
                return request(action, **values)
            keep = root / 'keep.skip'
            keep.write_bytes(b'keep local bytes')
            with patch.object(client, 'request', side_effect=valid):
                store.execute_push(job['id'], client)
            self.assertFalse(junk.exists())
            self.assertTrue(keep.exists(), 'custom exclusions never authorize local deletion')

    def test_current_mappings_drop_unused_baselines_without_moving_files(self):
        with TemporaryDirectory() as directory:
            store, client = MirrorJobs(directory), MirrorClient()
            job, _ = store.create(client, 'Secret', 'private folder title')
            target = store.target(job)
            (target / 'opaque-name').write_bytes(b'local edits')
            records = json.loads(store.path.read_bytes())
            records['schema'] = 3
            records['jobs'][0]['baseline'] = {'opaque-name': 'd' * 64}
            store.path.write_text(json.dumps(records))
            before = store.path.read_bytes()
            restored = MirrorJobs(directory)
            self.assertFalse(restored.error)
            self.assertNotIn('baseline', restored.jobs[job['id']])
            self.assertEqual(store.path.read_bytes(), before, 'Loading must not rewrite records')
            restored.save()
            self.assertEqual(json.loads(store.path.read_bytes())['schema'], 4)
            self.assertEqual(restored.target(job), target)
            self.assertEqual((target / 'opaque-name').read_bytes(), b'local edits')

    def test_empty_subfolder_push_and_stable_source_snapshot(self):
        with TemporaryDirectory() as directory:
            store, client = MirrorJobs(directory), MirrorClient()
            job, _ = store.create(client, 'Remote', 'folder')
            (store.target(job) / 'empty').mkdir()
            self.assertEqual(store.execute_push(job['id'], client), 0)
            self.assertIn('folder/empty', client.directories)
            self.assertNotIn('baseline', store.jobs[job['id']])
            self.assertNotIn('baseline', json.loads(store.path.read_text())['jobs'][0])

    def test_metadata_inspection_reads_no_contents_and_rejects_crypt_hardlinks(self):
        with TemporaryDirectory() as directory:
            store, client = MirrorJobs(directory), MirrorClient()
            job, _ = store.create(client, 'Remote', 'folder')
            with patch.object(Path, 'open', side_effect=AssertionError('No content reads')):
                self.assertIn('note.txt', store.inspect(store.target(job), copy_links=True))
            secret, _ = store.create(client, 'Secret', 'private')
            os.link(store.target(secret) / 'opaque-name', store.target(secret) / 'hard-linked')
            with self.assertRaisesRegex(ValueError, 'unsupported entry'):
                store.execute_push(secret['id'], client)

    def test_crypt_mutation_during_native_authentication_blocks_sync(self):
        with TemporaryDirectory() as directory:
            store, client = MirrorJobs(directory), MirrorClient()
            job, _ = store.create(client, 'Secret', 'private')
            original = client.request
            def changed(action, **values):
                result = original(action, **values)
                if action == 'mirror_validate':
                    (store.target(job) / 'opaque-name').write_bytes(b'changed during authentication')
                if action == 'mirror_sync':
                    raise AssertionError('Changed ciphertext was uploaded')
                return result
            with patch.object(client, 'request', side_effect=changed):
                with self.assertRaisesRegex(ValueError, 'changed during validation'):
                    store.execute_push(job['id'], client)

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

    def test_review_execution_uses_exact_proposed_destination(self):
        with TemporaryDirectory() as directory:
            store, client = MirrorJobs(directory), MirrorClient()
            proposal = store.prepare_review(client, 'Remote', 'folder', storage='Local')
            reviewed = store.target(proposal)
            self.assertEqual(proposal['target'], 'folder')
            self.assertFalse(reviewed.exists())
            store.execute_review(proposal, client, new=True)
            self.assertEqual(store.target(store.jobs[proposal['id']]), reviewed)
            self.assertEqual((reviewed / 'note.txt').read_bytes(), b'first')
            changed = dict(proposal, target='other')
            with self.assertRaisesRegex(ValueError, 'destination changed'):
                store.execute_review(changed, client)
            self.assertFalse((store.root / 'LocalFiles' / 'other').exists())
            store.jobs.pop(proposal['id'])
            store.save()
            with self.assertRaisesRegex(ValueError, 'mapping changed'):
                store.execute_review(proposal, client)

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
            proposal = dict(job)
            external = store.path.read_bytes() + b'\n'
            store.path.write_bytes(external)
            with self.assertRaisesRegex(OSError, 'records changed'):
                store.execute_review(proposal, client, push=True)
            self.assertEqual(store.path.read_bytes(), external)
            self.assertEqual(client.data['folder/note.txt'], b'first')

    def test_plain_sync_removes_destination_only_files_within_selected_scope(self):
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
            self.assertEqual(store.execute_push(job['id'], client), 1)
            self.assertEqual({key for key in client.data if key.startswith('folder/')}, {'folder/added.txt'})
            self.assertEqual(client.data['elsewhere/keep.txt'], b'outside selected folder')
            self.assertEqual(client.backups, [])

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
            target.write_bytes(b'changed after review')
            client.identity = 'c' * 64
            with self.assertRaisesRegex(ValueError, 'connection changed'):
                store.execute_review(dict(job), client, push=True)
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
                store.execute_push(job['id'], client)

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
                with (patch.object(store, 'inspect', side_effect=AssertionError('No content scan')),
                      patch('commonUtils.runtime.resource_mutations.inventory', side_effect=AssertionError('No inventory'))):
                    store.delete_copy(job['id'])
                self.assertFalse(target.exists())
                self.assertTrue(sibling.exists())
                self.assertEqual(keep.read_text(), 'outside storage')
                self.assertNotIn(job['id'], MirrorJobs(directory).jobs)
                self.assertEqual(client.data['folder/note.txt'], b'first')

    def test_obsolete_recovery_records_are_preserved_without_running_a_migration(self):
        for schema in (1, 2):
            with self.subTest(schema=schema), TemporaryDirectory() as directory:
                store, client = MirrorJobs(directory), MirrorClient()
                job, _ = store.create(client, 'Remote', 'folder')
                backup = store.root / 'TransferSnapshots' / 'old-copy'
                backup.mkdir(parents=True)
                (backup / 'note.txt').write_bytes(b'preserve old data')
                records = json.loads(store.path.read_bytes())
                records.update(schema=schema, pending=None)
                store.path.write_text(json.dumps(records))
                original = store.path.read_bytes()
                restored = MirrorJobs(directory)
                self.assertTrue(restored.error)
                with self.assertRaises(ValueError):
                    restored.create(client, 'Remote', 'folder')
                self.assertEqual(store.path.read_bytes(), original)
                self.assertTrue(store.target(job).exists())
                self.assertEqual((backup / 'note.txt').read_bytes(), b'preserve old data')

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
        from features.rclone.transfers.mobile.ui import MirrorUI
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
        live = dict(phase='Transferring', files=2, total_files=4, done=12_500_000, total=25_000_000, active=1)
        for _ in range(3):
            MirrorUI.publish_mirror_progress(app, 1, live)
        bar.stop.assert_called_once()
        origin.stop.assert_called_once()
        self.assertEqual(bar.value, 50)
        self.assertIn('50% of known work', app.transfer_message)
        self.assertIn('2 file(s) completed / 4 known', app.transfer_message)
        self.assertIn('1 transferring', app.transfer_message)
        self.assertIn('12.50 / 25.00 MB (known so far)', app.transfer_message)
        MirrorUI.publish_mirror_progress(app, 1, dict(live, done=6_250_000))
        self.assertEqual(bar.value, 25)  # Byte progress takes precedence over files.
        self.assertIn('25% of known work', app.transfer_message)
        MirrorUI.publish_mirror_progress(app, 1, dict(phase='Transferring', files=0, done=32_250_000, total=0))
        self.assertIn('32.25 MB transferred', app.transfer_message)
        bar.start.assert_called_once()
        MirrorUI.publish_mirror_progress(app, 0, live)
        self.assertIsNone(bar.max)

    def test_file_total_fallback_and_unknown_totals(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from features.rclone.transfers.mobile.ui import MirrorUI
        bar = SimpleNamespace(max=None, value=0, start=Mock(), stop=Mock())
        app = SimpleNamespace(active_host=True, transfer_epoch=1, transfer_busy=True,
                              transfer_progress=bar, refresh_transfer_status=Mock(),
                              transfer_notice=SimpleNamespace(text=''), cloud_status=SimpleNamespace(value=''))
        for files, total_files, expected in ((1, 4, 25), (4, 4, 99), (5, 4, 99)):
            MirrorUI.publish_mirror_progress(app, 1, dict(phase='Checking', files=files,
                                                        total_files=total_files, done=0, total=0))
            self.assertEqual(bar.value, expected)
            self.assertIn(f'{expected}% of known work', app.transfer_message)
        MirrorUI.publish_mirror_progress(app, 1, dict(phase='Discovering', files=0, done=0, total=0))
        self.assertIsNone(app.transfer_percentage)
        self.assertNotIn('%', app.transfer_message)
        self.assertIsNone(bar.max)

    def test_reopening_details_and_banner_keep_known_percentage(self):
        import weakref
        import toga
        from types import SimpleNamespace
        from unittest.mock import Mock
        from features.rclone.transfers.mobile.ui import MirrorUI
        parent, banner = toga.Box(), toga.Box()
        banner.notice = toga.Button('Details')
        banner.dismiss = toga.Button('Dismiss')
        banner.progress = toga.ProgressBar(max=100, value=0)
        app = SimpleNamespace(transfer_busy=True, transfer_percentage=42,
                              transfer_message='Transferring · 42% of known work',
                              mirror_store=lambda: SimpleNamespace(error=''),
                              show_view=Mock(), cancel_mirror_transfer=Mock(),
                              transfer_banners=[(weakref.ref(parent), weakref.ref(banner))])
        MirrorUI.show_transfers(app, present=False)
        self.assertEqual(app.transfer_progress.max, 100)
        self.assertEqual(app.transfer_progress.value, 42)
        MirrorUI.refresh_transfer_status(app)
        self.assertIn('42% of known work', banner.notice.text)
        self.assertEqual(banner.progress.value, 42)
