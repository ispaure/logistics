"""Drive migration preserves bytes, private records and unavailable-card boundaries."""
import errno
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from features.rclone.mobile.storage_location import (
    CONFIG, MARKER, CollectionFiles, collection_path, switch_location,
    recover_location, wipe_destination, start_empty_location, describe_location,
)
from features.rclone.transfers.mobile.jobs import MirrorJobs
from test_mirror_jobs import MirrorClient
from logisticsmobile.folder_hub import hub_entries


class CollectionStorageTests(unittest.TestCase):
    def test_start_empty_keeps_old_files_and_private_metadata_and_never_overwrites(self):
        self.seed()
        self.assertTrue(start_empty_location(self.private, self.volume))
        self.assertFalse(list(collection_path(self.private).iterdir()))
        self.assertFalse(list(collection_path(self.private, True).iterdir()))
        self.assertTrue(any((self.private / 'LocalFiles').rglob('note.txt')))
        self.assertEqual((self.private / 'credentials.bin').read_bytes(), b'stay internal')
        (collection_path(self.private) / 'new.txt').write_text('new')
        with self.assertRaises(FileExistsError):
            start_empty_location(self.private, self.volume)
        self.assertEqual((collection_path(self.private) / 'new.txt').read_text(), 'new')

    def test_empty_selection_can_recover_from_missing_active_card(self):
        self.seed()
        switch_location(self.private, self.volume)
        self.volume.rename(self.base / 'removed-card')
        other = self.base / 'new-card'
        other.mkdir()
        self.assertTrue(start_empty_location(self.private, other))
        self.assertEqual(collection_path(self.private), other / 'Logistics/Local')
        self.assertTrue(any((self.base / 'removed-card/Logistics/Local').rglob('note.txt')))

    def test_inspect_is_read_only_and_identifies_active_vs_other_location(self):
        self.assertTrue(describe_location(self.private, None)['active'])
        description = describe_location(self.private, self.volume)
        self.assertFalse(description['active'])
        self.assertEqual([state for _, state in description['folders']], ['not created', 'not created'])
        self.assertFalse((self.volume / 'Logistics').exists())
        start_empty_location(self.private, self.volume)
        self.assertTrue(describe_location(self.private, self.volume)['active'])
    def test_progress_reports_real_chunks_and_only_completes_after_activation(self):
        self.seed()
        (self.private / 'LocalFiles/large.bin').write_bytes(b'x' * (3 * 1024 * 1024))
        events = []
        def record(event):
            events.append(event)
            if event['phase'] == 'Complete':
                self.assertEqual(collection_path(self.private), self.volume / 'Logistics/Local')
        import itertools
        with patch('features.rclone.mobile.storage_location.time.monotonic', side_effect=itertools.count()):
            switch_location(self.private, self.volume, progress=record)
        copy = [event for event in events if event['phase'] == 'Copying Local']
        self.assertTrue(any(0 < event['bytes'] < event['total'] for event in copy))
        self.assertEqual(copy[-1]['bytes'], copy[-1]['total'])
        self.assertEqual([event['bytes'] for event in copy], sorted(event['bytes'] for event in copy))
        self.assertTrue(any(event['path'].endswith('large.bin') for event in copy))
        self.assertIn('Final verification', [event['phase'] for event in events])
        self.assertEqual(events[-1]['phase'], 'Complete')

    def test_small_file_progress_is_throttled_and_folder_completion_is_flushed(self):
        source = self.private / 'LocalFiles'
        source.mkdir()
        for index in range(200):
            (source / str(index)).write_bytes(b'x')
        events = []
        with patch('features.rclone.mobile.storage_location.time.monotonic', return_value=0):
            switch_location(self.private, self.volume, progress=events.append)
        copy = [event for event in events if event['phase'] == 'Copying Local']
        self.assertEqual(len(copy), 2)  # initial and final; no per-file queue flood
        self.assertEqual((copy[-1]['files'], copy[-1]['bytes'], copy[-1]['total']), (200, 200, 200))
        self.assertEqual(events[-1]['phase'], 'Complete')
        self.assertEqual(len(list(collection_path(self.private).iterdir())), 200)

    def test_progress_failure_never_reports_complete_or_changes_location(self):
        self.seed()
        events = []
        with patch('features.rclone.mobile.storage_location._sync', side_effect=OSError('Card removed')):
            with self.assertRaisesRegex(OSError, 'Card removed'):
                switch_location(self.private, self.volume, progress=events.append)
        self.assertNotIn('Complete', [event['phase'] for event in events])
        self.assertFalse((self.private / CONFIG).exists())
        self.assertEqual(list((self.volume / 'Logistics').glob('.storage-copy-*')), [])

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.private = self.base / 'private'
        self.volume = self.base / 'card'
        self.private.mkdir()
        self.volume.mkdir()

    def seed(self):
        store, client = MirrorJobs(self.private), MirrorClient()
        local, _ = store.create(client, 'Remote', 'folder')
        crypt, _ = store.create(client, 'Secret', 'secret')
        (self.private / 'credentials.bin').write_bytes(b'stay internal')
        return store, client, local, crypt

    def test_both_trees_switch_and_transfers_keep_private_metadata(self):
        store, client, local, crypt = self.seed()
        original = store.path.read_bytes()
        old = store.target(local)
        self.assertTrue(switch_location(self.private, self.volume))
        self.assertEqual(collection_path(self.private), self.volume / 'Logistics/Local')
        self.assertEqual(collection_path(self.private, True), self.volume / 'Logistics/LocalCrypt')
        self.assertEqual((store.target(local) / 'note.txt').read_bytes(), b'first')
        self.assertEqual((store.target(crypt) / 'opaque-name').read_bytes(), b'ciphertext')
        self.assertTrue(old.is_dir())
        self.assertEqual(store.path.read_bytes(), original)
        self.assertFalse((self.volume / 'Logistics/credentials.bin').exists())
        client.data['folder/note.txt'] = b'updated'
        store.pull(local['id'], client)
        self.assertEqual((store.target(local) / 'note.txt').read_bytes(), b'updated')
        self.assertEqual((old / 'note.txt').read_bytes(), b'first')
        self.assertTrue(any(row[0] == 'Remote' for row in hub_entries(self.private, store.jobs)))

    def test_card_removal_never_creates_fallback_and_retained_provider_stops(self):
        store, client, local, crypt = self.seed()
        switch_location(self.private, self.volume)
        provider = CollectionFiles(self.private)
        self.volume.rename(self.base / 'removed')
        with self.assertRaisesRegex(OSError, 'drive unavailable'):
            provider.mkdir('must-not-exist')
        with self.assertRaisesRegex(OSError, 'drive unavailable'):
            store.pull(local['id'], client)
        self.assertFalse(self.volume.exists())
        self.assertFalse((self.private / 'LocalFiles/must-not-exist').exists())
        self.assertEqual([row[0] for row in hub_entries(self.private, store.jobs, ['Cloud'])], ['Cloud'])

    def test_conflict_leaves_selection_and_sources_unchanged(self):
        store, client, local, crypt = self.seed()
        target = self.volume / 'Logistics/Local/different.txt'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'existing')
        with self.assertRaises(FileExistsError):
            switch_location(self.private, self.volume)
        self.assertFalse((self.private / CONFIG).exists())
        self.assertEqual(target.read_bytes(), b'existing')
        self.assertEqual((store.target(local) / 'note.txt').read_bytes(), b'first')

    def test_copy_failure_and_changed_source_do_not_commit(self):
        self.seed()
        with patch('features.rclone.mobile.storage_location.shutil.copytree', side_effect=OSError('disk removed')):
            with self.assertRaises(OSError):
                switch_location(self.private, self.volume)
        self.assertFalse((self.private / CONFIG).exists())
        self.assertEqual(list((self.volume / 'Logistics').glob('.storage-copy-*')), [])

    def test_symlink_and_wrong_card_marker_are_rejected(self):
        self.seed()
        (self.private / 'LocalFiles/escape').symlink_to(self.base, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Linked'):
            switch_location(self.private, self.volume)
        (self.private / 'LocalFiles/escape').unlink()
        switch_location(self.private, self.volume)
        (self.volume / 'Logistics' / MARKER).write_text('0' * 32)
        with self.assertRaisesRegex(ValueError, 'does not match'):
            collection_path(self.private)

    def test_existing_external_collection_can_be_adopted_without_overwrite(self):
        target = self.volume / 'Logistics/Local/books/comic.cbz'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'existing comic')
        switch_location(self.private, self.volume)
        self.assertEqual(target.read_bytes(), b'existing comic')
        self.assertFalse(switch_location(self.private, self.volume))

    def test_return_to_internal_requires_matching_backup(self):
        store, client, local, crypt = self.seed()
        switch_location(self.private, self.volume)
        self.assertTrue(switch_location(self.private, None))
        self.assertEqual(collection_path(self.private), self.private / 'LocalFiles')
        switch_location(self.private, self.volume)
        (store.target(local) / 'note.txt').write_bytes(b'new SD edit')
        with self.assertRaises(FileExistsError):
            switch_location(self.private, None)
        self.assertEqual(collection_path(self.private), self.volume / 'Logistics/Local')

    def test_recover_internal_backup_with_missing_card(self):
        store, client, local, crypt = self.seed()
        switch_location(self.private, self.volume)
        self.volume.rename(self.base / 'removed')
        self.assertTrue(recover_location(self.private, None))
        self.assertEqual((store.target(local) / 'note.txt').read_bytes(), b'first')
        self.assertFalse((self.private / CONFIG).exists())
        self.assertFalse(self.volume.exists())

    def test_recovery_repairs_config_and_keeps_existing_destination(self):
        self.seed()
        target = self.volume / 'Logistics/Local/book.epub'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'older backup')
        (self.private / CONFIG).write_text('{broken')
        recover_location(self.private, self.volume)
        self.assertEqual(collection_path(self.private), target.parent)
        self.assertEqual(target.read_bytes(), b'older backup')
        self.assertTrue((self.private / 'LocalFiles').is_dir())

    def test_wipe_conflict_then_retry_preserves_other_data(self):
        store, client, local, crypt = self.seed()
        base = self.volume / 'Logistics'
        (base / 'Local').mkdir(parents=True)
        (base / 'Local/old').write_bytes(b'old destination')
        (base / '.storage-copy-interrupted').mkdir()
        (base / '.storage-copy-interrupted/partial').write_bytes(b'partial')
        (base / 'unrelated').write_bytes(b'keep')
        (base / MARKER).write_text('broken marker')
        wipe_destination(self.private, self.volume)
        self.assertFalse((base / 'Local').exists())
        self.assertFalse(list(base.glob('.storage-copy-*')))
        self.assertFalse((base / MARKER).exists())
        self.assertEqual((base / 'unrelated').read_bytes(), b'keep')
        self.assertEqual((self.private / 'credentials.bin').read_bytes(), b'stay internal')
        switch_location(self.private, self.volume)
        self.assertEqual((store.target(local) / 'note.txt').read_bytes(), b'first')

    def test_wipe_active_and_linked_destination_rejected(self):
        self.seed()
        with self.assertRaisesRegex(ValueError, 'active collection'):
            wipe_destination(self.private, None)
        base = self.volume / 'Logistics'
        base.mkdir()
        (base / 'Local').symlink_to(self.private / 'LocalFiles', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Linked'):
            wipe_destination(self.private, self.volume)
        self.assertTrue((self.private / 'LocalFiles').is_dir())

    def test_recovery_requires_existing_data_and_validates_links(self):
        with self.assertRaisesRegex(ValueError, 'No existing collection'):
            recover_location(self.private, self.volume)
        self.assertFalse((self.private / CONFIG).exists())

        base = self.volume / 'Logistics'
        base.mkdir(parents=True)
        (base / 'Local').symlink_to(self.private, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Linked'):
            recover_location(self.private, self.volume)
        self.assertFalse((self.private / CONFIG).exists())

    def test_unreadable_recovery_root_never_activates(self):
        tree = self.volume / 'Logistics/Local'
        tree.mkdir(parents=True)
        original_stat = Path.stat
        def unreadable(path, *args, **kwargs):
            if path == tree:
                raise PermissionError('Storage access denied')
            return original_stat(path, *args, **kwargs)
        with patch.object(Path, 'stat', unreadable):
            with self.assertRaisesRegex(PermissionError, 'denied'):
                recover_location(self.private, self.volume)
        self.assertFalse((self.private / CONFIG).exists())

    def test_reconnect_after_reset_never_scans_or_reads_collection_contents(self):
        target = self.volume / 'Logistics/LocalCrypt/unreadable-file'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'retained ciphertext')
        original_open = Path.open
        def unreadable(path, *args, **kwargs):
            if path == target:
                raise OSError(errno.EIO, 'I/O error', str(path))
            return original_open(path, *args, **kwargs)
        events = []
        with patch.object(Path, 'open', unreadable), \
                patch('features.rclone.mobile.storage_location.os.walk', side_effect=AssertionError('Must not scan')), \
                patch('features.rclone.mobile.storage_location._inventory', side_effect=AssertionError('Must not hash')):
            self.assertTrue(recover_location(self.private, self.volume, progress=events.append))
        self.assertEqual(collection_path(self.private, True), target.parent)
        self.assertTrue(collection_path(self.private).is_dir())
        self.assertEqual(target.read_bytes(), b'retained ciphertext')
        self.assertEqual([event['phase'] for event in events], ['Checking location', 'Saving location', 'Complete'])

    def test_recovery_rejects_file_in_place_of_either_collection_folder(self):
        base = self.volume / 'Logistics'
        (base / 'Local').mkdir(parents=True)
        (base / 'LocalCrypt').write_bytes(b'not a folder')
        with self.assertRaisesRegex(ValueError, 'must be a folder'):
            recover_location(self.private, self.volume)
        self.assertFalse((self.private / CONFIG).exists())

    def test_android_filesystem_without_fsync_still_verifies_bytes(self):
        store, client, local, crypt = self.seed()
        from features.rclone.mobile.storage_location import _sync

        def unsupported_sync(stream):
            with patch('features.rclone.mobile.storage_location.os.fsync', side_effect=OSError(errno.EINVAL, 'unsupported')):
                _sync(stream)

        with patch('features.rclone.mobile.storage_location._sync', side_effect=unsupported_sync):
            switch_location(self.private, self.volume)
        self.assertEqual((store.target(local) / 'note.txt').read_bytes(), b'first')

    def test_real_sync_failure_never_commits(self):
        self.seed()
        with patch('features.rclone.mobile.storage_location.os.fsync', side_effect=OSError(errno.EIO, 'I/O error')):
            with self.assertRaises(OSError):
                switch_location(self.private, self.volume)
        self.assertFalse((self.private / CONFIG).exists())

    def test_interrupted_second_tree_retry_only_requires_remaining_space(self):
        from types import SimpleNamespace
        import shutil
        self.seed()
        (self.private / 'LocalFiles/large.bin').write_bytes(b'x' * (2 * 1024 * 1024))
        original_copy = shutil.copytree

        def fail_crypt(source, target, *args, **kwargs):
            if Path(source).name == 'LocalCryptFolders':
                raise OSError('Card disconnected')
            return original_copy(source, target, *args, **kwargs)

        with patch('features.rclone.mobile.storage_location.shutil.copytree', side_effect=fail_crypt):
            with self.assertRaisesRegex(OSError, 'disconnected'):
                switch_location(self.private, self.volume)
        self.assertFalse((self.private / CONFIG).exists())
        with patch('features.rclone.mobile.storage_location.shutil.disk_usage', return_value=SimpleNamespace(free=2 * 1024 * 1024)):
            self.assertTrue(switch_location(self.private, self.volume))
        self.assertEqual((collection_path(self.private) / 'large.bin').stat().st_size, 2 * 1024 * 1024)
