"""Visible received-file roots and lossless upgrades from legacy Inbox storage."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from commonUtils.persistence import atomic_write_json
from services.documents.locations import (
    _shared_local_roots, use_shared_local, switch_location, collection_path,
)
from mobile.incoming_files import inbox_path
from mobile.local_sources import device_files


class ReceivedFilesTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.private = self.base / 'Private'
        self.private.mkdir()
        self.volume = self.base / 'Volume'
        self.volume.mkdir()
        self.addCleanup(_shared_local_roots.pop, self.private, None)

    def legacy(self, base=None):
        source = (base or self.private) / 'Inbox'
        (source / 'nested').mkdir(parents=True)
        (source / 'nested/été.txt').write_bytes(b'original bytes')
        return source

    def test_android_external_upgrade_preserves_existing_files_and_does_not_repeat(self):
        switch_location(self.private, self.volume)
        source = self.legacy()
        received = self.volume / 'Logistics/Received Files'
        (received / 'hello.txt').write_bytes(b'existing destination')
        self.assertEqual(inbox_path(self.private), received)
        self.assertEqual((received / 'Previous Inbox/nested/été.txt').read_bytes(), b'original bytes')
        self.assertEqual((source / 'nested/été.txt').read_bytes(), b'original bytes')
        self.assertEqual((received / 'hello.txt').read_bytes(), b'existing destination')
        inbox_path(self.private)
        self.assertEqual({p.name for p in received.iterdir()}, {'hello.txt', 'Previous Inbox'})

    def test_ios_read_only_system_inbox_is_copied_to_visible_received_files(self):
        documents = self.base / 'Documents'
        documents.mkdir()
        source = self.legacy(documents)
        use_shared_local(self.private, documents)
        original = Path.mkdir
        def protected(path, *args, **kwargs):
            if path == source:
                raise PermissionError('system Inbox')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'mkdir', protected):
            received = inbox_path(self.private)
        self.assertEqual(received, documents / 'Received Files')
        self.assertEqual((received / 'nested/été.txt').read_bytes(), b'original bytes')
        self.assertEqual((source / 'nested/été.txt').read_bytes(), b'original bytes')
        self.assertIn('Received Files', [row['name'] for row in device_files(self.private).list()])

    def test_upgrade_interrupted_after_publication_reuses_same_target(self):
        self.legacy()
        def fail_completion(path, value, **kwargs):
            if value.get('done'):
                raise OSError('interrupted after publication')
            return atomic_write_json(path, value, **kwargs)
        with patch('mobile.incoming_files.atomic_write_json', side_effect=fail_completion):
            with self.assertRaisesRegex(OSError, 'interrupted'):
                inbox_path(self.private)
        received = inbox_path(self.private)
        self.assertEqual({p.name for p in received.iterdir()}, {'nested'})
        self.assertEqual((received / 'nested/été.txt').read_bytes(), b'original bytes')

    def test_partial_copy_failure_keeps_original_and_retry_succeeds(self):
        source = self.legacy()
        with patch('services.documents.locations._copy_durable', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                inbox_path(self.private)
        self.assertEqual((source / 'nested/été.txt').read_bytes(), b'original bytes')
        received = inbox_path(self.private)
        self.assertEqual((received / 'nested/été.txt').read_bytes(), b'original bytes')
        self.assertEqual(list(self.private.glob('.storage-copy-*')), [])

    def test_linked_legacy_files_are_rejected_and_preserved(self):
        source = self.legacy()
        (source / 'linked').symlink_to(source / 'nested/été.txt')
        with self.assertRaisesRegex(ValueError, 'Linked'):
            inbox_path(self.private)
        self.assertEqual((source / 'nested/été.txt').read_bytes(), b'original bytes')

    def test_changed_published_upgrade_preserves_both_versions(self):
        source = self.legacy()
        # Interrupt after publication but before the completion receipt.
        original = atomic_write_json
        def fail_done(path, value, **kwargs):
            if value.get('done'):
                raise OSError('interrupted')
            return original(path, value, **kwargs)
        with patch('mobile.incoming_files.atomic_write_json', side_effect=fail_done):
            with self.assertRaises(OSError):
                inbox_path(self.private)
        target = self.private / 'Received Files/nested/été.txt'
        target.write_bytes(b'user edit')
        with self.assertRaisesRegex(FileExistsError, 'both copies'):
            inbox_path(self.private)
        self.assertEqual(target.read_bytes(), b'user edit')
        self.assertEqual((source / 'nested/été.txt').read_bytes(), b'original bytes')

    def test_android_browse_root_exposes_only_local_and_received_and_guards_old_drive(self):
        (self.private / 'credentials.bin').write_bytes(b'private')
        provider = device_files(self.private)
        self.assertEqual([row['name'] for row in provider.list()], ['Local', 'Received Files'])
        for path in ('credentials.bin', 'LocalCryptFolders', 'Inbox'):
            with self.assertRaises(ValueError):
                provider.entry(path)
        with self.assertRaisesRegex(ValueError, 'managed'):
            provider.rename('Received Files', 'LocalFiles/received')
        switch_location(self.private, self.volume)
        with self.assertRaisesRegex(ValueError, 'changed'):
            provider.list()
        self.assertEqual([row['path'] for row in device_files(self.private).list()], ['Local', 'Received Files'])

    def test_received_files_follow_drive_copy_with_original_backup(self):
        received = inbox_path(self.private)
        (received / 'hello.txt').write_bytes(b'keep me')
        switch_location(self.private, self.volume)
        self.assertEqual(inbox_path(self.private), self.volume / 'Logistics/Received Files')
        self.assertEqual((inbox_path(self.private) / 'hello.txt').read_bytes(), b'keep me')
        self.assertEqual((received / 'hello.txt').read_bytes(), b'keep me')
        self.volume.rename(self.base / 'Disconnected')
        with self.assertRaisesRegex(OSError, 'unavailable'):
            inbox_path(self.private)
        self.assertEqual((received / 'hello.txt').read_bytes(), b'keep me')

    def test_android_browse_all_and_workspace_use_same_received_files(self):
        from mobile.app import LogisticsMobile
        from mobile.folder_hub import FolderDiscoverySnapshot, discover_folder_choices
        LogisticsMobile.storage_root = self.private
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(app.loop.close)
        self.addCleanup(app.main_window.close)
        received = inbox_path(app.private_root)
        (received / 'shared.txt').write_bytes(b'shared')
        choices = discover_folder_choices(FolderDiscoverySnapshot(app.private_root, {}, (), (), (), {})).choices
        self.assertEqual(choices['All files']['kind'], 'shared-local')
        self.assertEqual(choices['Received Files']['kind'], 'inbox')
        app.loop.run_until_complete(app.show_files(location=('Shared files', '')))
        row = next(row for row in app.file_rows.values() if row['name'] == 'Received Files')
        app.loop.run_until_complete(app.browser_file_folder(row))
        self.assertEqual([row['name'] for row in app.file_rows.values()], ['shared.txt'])
        app.loop.run_until_complete(app.show_files(location=('Received Files', '')))
        self.assertEqual(app.file_provider.root, received)
        self.assertEqual([row['name'] for row in app.file_rows.values()], ['shared.txt'])
