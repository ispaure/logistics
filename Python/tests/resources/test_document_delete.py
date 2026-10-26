"""Shared deletion admits only a writable, declared, stable file revision."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from commonUtils.runtime.operations import OperationCancelled
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.provider import ResourceCapabilities
from services.documents.storage import DocumentResource
from features.notebooks.recovery import Repository


class DocumentDeleteTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'document.bin'
        self.path.write_bytes(b'original')
        self.provider = LocalFiles(self.root)
        self.resource = DocumentResource(self.provider, self.path, max_bytes=100)
        self.addCleanup(self.resource.close)

    def test_unread_cancelled_stale_and_closed_deletion_preserve_source(self):
        with self.assertRaisesRegex(ValueError, 'Read the document'):
            self.resource.delete()
        self.resource.read()
        with self.assertRaises(OperationCancelled):
            self.resource.delete(cancelled=lambda: True)
        self.path.write_bytes(b'external edit')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.resource.delete()
        self.resource.close()
        with self.assertRaisesRegex(ValueError, 'closed'):
            self.resource.delete()
        self.assertEqual(self.path.read_bytes(), b'external edit')

    def test_readonly_wrappers_and_missing_delete_capability_are_denied(self):
        self.resource.read()
        for wrapped in (SimpleNamespace(remote_storage=True), SimpleNamespace(read_only=True),
                        SimpleNamespace(capabilities=ResourceCapabilities(replace=True))):
            self.provider.provider = wrapped
            with self.subTest(wrapped=wrapped), self.assertRaises(PermissionError):
                self.resource.delete()
        self.assertEqual(self.path.read_bytes(), b'original')

    def test_provider_rechecks_revision_at_actual_mutation(self):
        self.resource.read()
        remove = self.provider.remove_empty
        def raced(path, revision):
            self.path.write_bytes(b'racing replacement')
            return remove(path, revision)
        with patch.object(self.provider, 'remove_empty', side_effect=raced):
            with self.assertRaises(ValueError):
                self.resource.delete()
        self.assertEqual(self.path.read_bytes(), b'racing replacement')

    def test_success_deletes_file_and_directory_resources_are_denied(self):
        self.resource.read()
        self.resource.delete()
        self.assertFalse(self.path.exists())
        folder = self.root / 'folder'
        folder.mkdir()
        with DocumentResource(self.provider, folder, max_bytes=100) as resource:
            resource.revision = self.provider.entry('folder')['revision']
            with self.assertRaises(ValueError):
                resource.delete()
        self.assertTrue(folder.is_dir())

    def test_recovery_deletion_is_identity_bounded_and_missing_is_idempotent(self):
        repository = Repository(self.root / 'recovery')
        repository.delete('a' * 32)
        with self.assertRaises(ValueError):
            repository.delete('../outside')
        self.assertTrue(self.path.exists())
