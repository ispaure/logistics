"""Native ready handoff publication, conflict and recovery contracts."""
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from mobile.incoming_files import consume, inbox_path, valid_name
from features.rclone.mobile.storage_location import use_shared_local, _shared_local_roots


class IncomingTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.queue = self.root / 'incoming'
        self.queue.mkdir()
        self.inbox = inbox_path(self.root)

    def delivery(self, name='hello.txt', data=b'hello'):
        path = self.queue / (uuid4().hex + '.ready')
        path.mkdir()
        (path / 'metadata.json').write_text(json.dumps(dict(name=name)))
        (path / 'payload').write_bytes(data)
        return path

    def test_one_many_unicode_and_duplicates_preserve_bytes(self):
        self.delivery()
        self.delivery(data=b'other')
        self.delivery(name='été.txt', data=b'unicode')
        self.assertEqual(consume(self.queue, self.inbox), (3, 0))
        self.assertEqual({p.read_bytes() for p in self.inbox.iterdir()}, {b'hello', b'other', b'unicode'})
        self.assertTrue((self.inbox / 'hello (1).txt').exists())
        self.assertEqual(consume(self.queue, self.inbox), (0, 0))

    def test_existing_user_file_is_never_overwritten(self):
        (self.inbox / 'hello.txt').write_bytes(b'user data')
        self.delivery()
        self.assertEqual(consume(self.queue, self.inbox), (1, 0))
        self.assertEqual((self.inbox / 'hello.txt').read_bytes(), b'user data')
        self.assertEqual((self.inbox / 'hello (1).txt').read_bytes(), b'hello')

    def test_unready_and_invalid_records_are_preserved(self):
        partial = self.queue / (uuid4().hex + '.partial')
        partial.mkdir()
        bad = self.delivery(name='../escape')
        self.assertEqual(consume(self.queue, self.inbox), (0, 1))
        self.assertTrue(partial.exists())
        self.assertTrue(bad.exists())
        self.assertEqual(list(self.inbox.iterdir()), [])

    def test_symlinked_payload_metadata_destination_and_queue_are_rejected(self):
        outside = self.root / 'outside'
        outside.write_bytes(b'do not modify')
        delivery = self.delivery()
        (delivery / 'payload').unlink()
        (delivery / 'payload').symlink_to(outside)
        self.assertEqual(consume(self.queue, self.inbox), (0, 1))
        self.assertEqual(outside.read_bytes(), b'do not modify')
        linked = self.root / 'linked'
        linked.symlink_to(self.queue, target_is_directory=True)
        with self.assertRaises(ValueError):
            consume(linked, self.inbox)

    def test_partial_copy_failure_retains_ready_source_and_cleans_temporary(self):
        delivery = self.delivery()
        with patch('mobile.incoming_files.shutil.copyfileobj', side_effect=OSError('full')):
            self.assertEqual(consume(self.queue, self.inbox), (0, 1))
        self.assertEqual((delivery / 'payload').read_bytes(), b'hello')
        self.assertEqual(list(self.inbox.iterdir()), [])
        self.assertEqual(consume(self.queue, self.inbox), (1, 0))

    def test_interrupted_publication_retries_without_a_duplicate(self):
        delivery = self.delivery()
        with patch('mobile.incoming_files.shutil.rmtree', side_effect=OSError('interrupted')):
            self.assertEqual(consume(self.queue, self.inbox), (0, 1))
        self.assertEqual(consume(self.queue, self.inbox), (1, 0))
        self.assertEqual([p.name for p in self.inbox.iterdir()], ['hello.txt'])
        self.assertFalse(delivery.exists())

    def test_changed_destination_after_interruption_preserves_both_copies(self):
        delivery = self.delivery()
        (delivery / 'receipt.json').write_text(json.dumps(dict(name='hello.txt',
            sha256=sha256(b'hello').hexdigest(), size=5)))
        (self.inbox / 'hello.txt').write_bytes(b'changed')
        self.assertEqual(consume(self.queue, self.inbox), (0, 1))
        self.assertEqual((self.inbox / 'hello.txt').read_bytes(), b'changed')
        self.assertTrue(delivery.exists())

    def test_limits_hostile_names_and_oversized_unknown_streams(self):
        for name in ('', '.', '..', '/absolute', 'a/b', 'a\\b', 'a\0b', 'a\nb', 'x' * 241):
            with self.assertRaises(ValueError):
                valid_name(name)
        delivery = self.delivery(data=b'123456')
        with patch('mobile.incoming_files.MAX_FILE', 5):
            self.assertEqual(consume(self.queue, self.inbox), (0, 1))
        self.assertTrue(delivery.exists())

    def test_ios_inbox_is_sibling_of_shared_local(self):
        documents = self.root / 'Documents'
        private = self.root / 'Private'
        use_shared_local(private, documents)
        self.addCleanup(_shared_local_roots.pop, private, None)
        self.assertEqual(inbox_path(private), documents / 'Received Files')

    def test_existing_workspace_named_inbox_is_not_replaced(self):
        from mobile.folder_hub import FolderDiscoverySnapshot, discover_folder_choices
        folder = self.root / 'LocalFiles/Received Files'
        folder.mkdir(parents=True)
        (folder / 'keep.txt').write_bytes(b'existing workspace')
        snapshot = FolderDiscoverySnapshot(self.root, {}, (), (), (), {})
        choices = discover_folder_choices(snapshot).choices
        self.assertEqual(choices['Received Files']['kind'], 'local')
        self.assertEqual(choices['Received Files (received)']['kind'], 'inbox')
        self.assertEqual((folder / 'keep.txt').read_bytes(), b'existing workspace')

    def test_stale_destination_temporary_is_recovered(self):
        delivery = self.delivery()
        (self.inbox / ('.incoming-' + delivery.name)).write_bytes(b'incomplete')
        self.assertEqual(consume(self.queue, self.inbox), (1, 0))
        self.assertEqual([p.name for p in self.inbox.iterdir()], ['hello.txt'])

    def test_failed_delivery_waits_for_restart_instead_of_recopying_every_poll(self):
        delivery = self.delivery(name='../escape')
        failed = set()
        self.assertEqual(consume(self.queue, self.inbox, failed_deliveries=failed), (0, 1))
        self.assertIn(delivery.name, failed)
        self.assertEqual(consume(self.queue, self.inbox, failed_deliveries=failed), (0, 0))
        self.assertEqual(consume(self.queue, self.inbox), (0, 1))

    def test_native_failure_marker_is_reported_once(self):
        (self.queue / 'failed').write_text('failed')
        self.assertEqual(consume(self.queue, self.inbox), (0, 1))
        self.assertEqual(consume(self.queue, self.inbox), (0, 0))

    def test_long_unicode_duplicate_names_fit_filesystem_limit(self):
        name = 'é' * 115 + '.txt'
        self.delivery(name=name)
        self.delivery(name=name)
        self.assertEqual(consume(self.queue, self.inbox), (2, 0))
        self.assertTrue(all(len(p.name.encode('utf-8')) <= 240 for p in self.inbox.iterdir()))

    def test_abandoned_partial_expires_without_removing_a_recent_copy(self):
        import time
        old = self.queue / (uuid4().hex + '.partial')
        recent = self.queue / (uuid4().hex + '.partial')
        old.mkdir()
        recent.mkdir()
        then = time.time() - 25 * 60 * 60
        os.utime(old, (then, then))
        self.assertEqual(consume(self.queue, self.inbox), (0, 0))
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())

    def test_inbox_is_browsable_through_normal_android_file_roots(self):
        from mobile.app import LogisticsMobile
        LogisticsMobile.storage_root = self.root
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(app.loop.close)
        self.addCleanup(app.main_window.close)
        self.delivery()
        consume(self.queue, self.inbox)
        app.loop.run_until_complete(app.show_files(location=('Received Files', '')))
        self.assertEqual(app.file_provider.root, self.inbox)
        self.assertEqual([row['name'] for row in app.file_rows.values()], ['hello.txt'])
