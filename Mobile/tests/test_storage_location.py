"""Drive migration preserves bytes, private records and unavailable-card boundaries."""
import errno
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from features.rclone.mobile.storage_location import (
    CONFIG, MARKER, CollectionFiles, collection_path, switch_location,
    recover_location, wipe_destination,
)
from features.rclone.transfers.mobile.jobs import MirrorJobs
from test_mirror_jobs import MirrorClient
from logisticsmobile.folder_hub import hub_entries


class CollectionStorageTests(unittest.TestCase):
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
        base = self.volume / 'Logistics/Local'
        base.mkdir(parents=True)
        (base / 'escape').symlink_to(self.private, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Linked'):
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
