"""iOS upgrade migration, shared Local routing and private-state boundaries."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from services.documents.locations import collection_path, CollectionFiles, _shared_local_roots
from features.rclone.transfers.mobile.jobs import MirrorJobs
from mobile.ios_storage import MIGRATION, prepare_storage, prepare_for_app
from mobile.documents import DocumentStore
from mobile.folder_hub import hub_entries
from mobile_build.tests.transfers.test_mirror_jobs import MirrorClient


class IOSStorageTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.documents = self.base / 'Documents'
        self.private = self.base / 'Library/Application Support/Logistics'
        self.documents.mkdir()
        self.exclude = Mock()
        self.addCleanup(_shared_local_roots.pop, self.private, None)

    def move(self, source, destination):
        # The iOS adapter uses NSFileManager's exclusive same-volume move.
        if destination.exists():
            raise FileExistsError(destination)
        source.rename(destination)

    def prepare(self, **kwargs):
        return prepare_storage(self.documents, self.private,
                               exclude_backup=self.exclude, move=kwargs.get('move', self.move))

    def seed(self):
        jobs = MirrorJobs(self.documents)
        client = MirrorClient()
        local, _ = jobs.create(client, 'Remote', 'folder')
        crypt, _ = jobs.create(client, 'Secret', 'secret')
        (self.documents / 'Credentials').mkdir()
        (self.documents / 'Credentials/credentials.bin').write_bytes(b'wrapped credentials')
        (self.documents / 'LocalCrypt').mkdir()
        (self.documents / 'LocalCrypt/ciphertext').write_bytes(b'encrypted offline copy')
        document = DocumentStore(self.documents / 'Documents').create('Saved.md', b'# saved')
        return jobs, local, crypt, document

    def test_upgrade_keeps_mappings_documents_and_crypt_private(self):
        jobs, local, crypt, document = self.seed()
        old_records = jobs.path.read_bytes()
        self.prepare()
        restored = MirrorJobs(self.private)
        self.assertEqual(restored.path.read_bytes(), old_records)
        self.assertEqual(collection_path(self.private), self.documents / 'Local')
        self.assertEqual(collection_path(self.private, True), self.private / 'LocalCryptFolders')
        self.assertEqual((restored.target(local) / 'note.txt').read_bytes(), b'first')
        self.assertEqual((restored.target(crypt) / 'opaque-name').read_bytes(), b'ciphertext')
        self.assertEqual((self.private / 'Credentials/credentials.bin').read_bytes(), b'wrapped credentials')
        self.assertEqual((self.private / 'LocalCrypt/ciphertext').read_bytes(), b'encrypted offline copy')
        self.assertEqual(DocumentStore(self.private / 'Documents').open(document.id).text, '# saved')
        self.assertEqual({p.name for p in self.documents.iterdir()}, {'Local', 'Received Files'})
        self.assertFalse((self.private / 'LocalFiles').exists())
        self.exclude.assert_called_once_with(self.documents)
        # Imported files are local, while pull still resolves the original mapping.
        (self.documents / 'Local/from-computer.txt').write_bytes(b'imported')
        self.assertEqual(CollectionFiles(self.private).entry('from-computer.txt')['size'], len(b'imported'))
        client = MirrorClient()
        client.data['folder/note.txt'] = b'updated'
        restored.pull(local['id'], client)
        self.assertEqual((restored.target(local) / 'note.txt').read_bytes(), b'updated')

    def test_empty_local_is_created_and_recreated_on_launch(self):
        self.prepare()
        local = self.documents / 'Local'
        self.assertTrue(local.is_dir())
        self.assertEqual(list(local.iterdir()), [])
        self.assertFalse(collection_path(self.private, True).exists())
        local.rmdir()
        self.prepare()
        self.assertTrue(local.is_dir())
        self.assertEqual(list(local.iterdir()), [])

    def test_system_inbox_is_never_created_or_modified(self):
        inbox = self.documents / 'Inbox'
        inbox.mkdir()
        incoming = inbox / 'incoming.md'
        incoming.write_bytes(b'# incoming document')
        original = Path.mkdir
        def protected_mkdir(path, *args, **kwargs):
            if path == inbox:
                raise PermissionError(1, 'Operation not permitted', str(path))
            return original(path, *args, **kwargs)
        with patch.object(Path, 'mkdir', protected_mkdir):
            self.prepare()
            self.prepare()
        self.assertEqual(incoming.read_bytes(), b'# incoming document')

    def test_upgrade_keeps_existing_received_files_visible_and_legacy_imports_preserved(self):
        (self.documents / 'LocalFiles').mkdir()
        received = self.documents / 'Received Files'
        received.mkdir()
        (received / 'keep.txt').write_bytes(b'visible user file')
        inbox = self.documents / 'Inbox'
        inbox.mkdir()
        (inbox / 'old.txt').write_bytes(b'legacy import')
        self.prepare()
        self.assertEqual((received / 'keep.txt').read_bytes(), b'visible user file')
        self.assertEqual((received / 'Previous Inbox/old.txt').read_bytes(), b'legacy import')
        self.assertEqual((inbox / 'old.txt').read_bytes(), b'legacy import')
        received.rename(self.documents / 'Saved Received Files')
        self.prepare()
        self.assertTrue(received.is_dir())
        self.assertEqual(list(received.iterdir()), [])

    def test_completed_layout_leaves_shared_root_files_in_place(self):
        self.prepare()
        existing = self.documents / 'old-remote'
        existing.mkdir()
        (existing / 'note.txt').write_bytes(b'existing')
        self.prepare()
        self.assertEqual((existing / 'note.txt').read_bytes(), b'existing')
        self.assertEqual(list((self.documents / 'Local').iterdir()), [])
        store = MirrorJobs(self.private)
        job, _ = store.create(MirrorClient(), 'Remote', 'folder')
        self.assertEqual(store.target(job).parent, self.documents / 'Local')
        self.assertEqual([row[0] for row in hub_entries(self.private, store.jobs)], ['Remote'])

    def test_new_install_and_later_launches_keep_user_files_in_shared_root(self):
        (self.documents / 'book.epub').write_bytes(b'book')
        (self.documents / 'Documents').mkdir()
        (self.documents / 'Documents/user.txt').write_bytes(b'user documents')
        self.prepare()
        # A name that used to be private is an ordinary user folder after migration.
        (self.documents / 'LocalCrypt').mkdir()
        (self.documents / 'LocalCrypt/user.txt').write_bytes(b'user folder')
        self.prepare()
        self.assertEqual((self.documents / 'book.epub').read_bytes(), b'book')
        self.assertEqual((self.documents / 'Documents/user.txt').read_bytes(), b'user documents')
        self.assertTrue((self.documents / 'LocalCrypt/user.txt').exists())
        self.assertFalse((self.private / 'LocalCrypt').exists())
        self.assertEqual(self.exclude.call_count, 2)

    def test_interruption_in_each_phase_resumes_without_copying_or_overwriting(self):
        for phase in ('private', 'local'):
            with self.subTest(phase=phase), TemporaryDirectory() as directory:
                base = Path(directory)
                documents, private = base / 'Documents', base / 'private'
                (documents / 'LocalFiles/empty').mkdir(parents=True)
                (documents / 'LocalFiles/a.txt').write_bytes(b'A')
                (documents / 'LocalFiles/b.txt').write_bytes(b'B')
                (documents / 'workspace.json').write_bytes(b'private state')
                calls = []
                def interrupt(source, destination):
                    self.move(source, destination)
                    if json.loads((private / MIGRATION).read_text())['phase'] == phase:
                        calls.append(source)
                        raise OSError('interrupted after move')
                with self.assertRaisesRegex(OSError, 'interrupted'):
                    prepare_storage(documents, private, exclude_backup=self.exclude, move=interrupt)
                self.assertEqual(len(calls), 1)
                prepare_storage(documents, private, exclude_backup=self.exclude, move=self.move)
                self.addCleanup(_shared_local_roots.pop, private, None)
                self.assertEqual((documents / 'Local/a.txt').read_bytes(), b'A')
                self.assertEqual((documents / 'Local/b.txt').read_bytes(), b'B')
                self.assertTrue((documents / 'Local/empty').is_dir())
                self.assertEqual((private / 'workspace.json').read_bytes(), b'private state')

    def test_private_and_local_conflicts_preserve_both_versions(self):
        self.seed()
        self.private.mkdir(parents=True)
        (self.private / 'Credentials').mkdir()
        with self.assertRaises(FileExistsError):
            self.prepare()
        self.assertTrue((self.documents / 'Credentials/credentials.bin').exists())
        (self.private / 'Credentials').rmdir()
        def conflict(source, destination):
            if source.name == 'LocalFiles':
                self.move(source, destination)
                (self.documents / 'Local' / next(destination.iterdir()).name).mkdir(parents=True)
            else:
                self.move(source, destination)
        with self.assertRaises(FileExistsError):
            self.prepare(move=conflict)
        self.assertTrue(any((self.private / 'LocalFiles').iterdir()))
        self.assertNotIn(self.private, _shared_local_roots)

    def test_backup_failure_prevents_migration_and_registration(self):
        self.seed()
        self.exclude.side_effect = OSError('backup exclusion failed')
        with self.assertRaisesRegex(OSError, 'backup exclusion'):
            self.prepare()
        self.assertTrue((self.documents / 'LocalFiles').exists())
        self.assertNotIn(self.private, _shared_local_roots)

    def test_links_and_invalid_journal_are_rejected(self):
        self.seed()
        self.private.mkdir(parents=True)
        (self.private / MIGRATION).write_text('{"phase":"private","names":["../escape"]}')
        with self.assertRaisesRegex(ValueError, 'journal'):
            self.prepare()
        (self.private / MIGRATION).unlink()
        (self.documents / 'Credentials').rename(self.documents / 'original')
        (self.documents / 'Credentials').symlink_to(self.documents / 'original')
        with self.assertRaisesRegex(ValueError, 'Linked'):
            self.prepare()

    def test_native_adapter_uses_private_support_and_checks_backup_result(self):
        manager = SimpleNamespace(moveItemAtPath=Mock(return_value=True))
        url = SimpleNamespace(setResourceValue=Mock(return_value=False))
        classes = {'NSFileManager': SimpleNamespace(defaultManager=manager),
                   'NSURL': SimpleNamespace(fileURLWithPath=Mock(return_value=url))}
        app = SimpleNamespace(paths=SimpleNamespace(data=self.documents,
                              config=self.base / 'Library/Application Support/Config'))
        with patch.dict(sys.modules, {'rubicon.objc': SimpleNamespace(ObjCClass=classes.__getitem__)}):
            with self.assertRaisesRegex(OSError, 'excluded from backup'):
                prepare_for_app(app)
        url.setResourceValue.assert_called_once_with(True, forKey='NSURLIsExcludedFromBackupKey', error=None)
        manager.moveItemAtPath.assert_not_called()

    def test_native_adapter_migration_and_move_failure(self):
        self.seed()
        url = SimpleNamespace(setResourceValue=Mock(return_value=True))
        manager = SimpleNamespace(moveItemAtPath=Mock(return_value=False))
        classes = {'NSFileManager': SimpleNamespace(defaultManager=manager),
                   'NSURL': SimpleNamespace(fileURLWithPath=Mock(return_value=url))}
        app = SimpleNamespace(paths=SimpleNamespace(data=self.documents,
                              config=self.base / 'Library/Application Support/Config'))
        with patch.dict(sys.modules, {'rubicon.objc': SimpleNamespace(ObjCClass=classes.__getitem__)}):
            with self.assertRaisesRegex(OSError, 'could not move'):
                prepare_for_app(app)
            self.assertTrue((self.documents / 'Credentials/credentials.bin').exists())
            self.assertNotIn(self.private, _shared_local_roots)
            def native_move(source, *, toPath, error):
                self.move(Path(source), Path(toPath))
                return True
            manager.moveItemAtPath.side_effect = native_move
            self.assertEqual(prepare_for_app(app), self.private)
        self.assertFalse((self.documents / 'Credentials').exists())
        self.assertTrue((self.private / 'Credentials/credentials.bin').exists())
