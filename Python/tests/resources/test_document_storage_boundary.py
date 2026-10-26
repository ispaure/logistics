"""Format editing stays independent of concrete storage implementations."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from commonUtils.runtime.resources.local import LocalFiles
from features.text_editor.notes import NotesLibrary
from services.documents.storage import DocumentPolicy, DocumentResource, publish_document_stream


class DocumentBoundaryTests(unittest.TestCase):
    def test_wrapped_remote_policy_cannot_become_writable_or_persistent(self):
        with TemporaryDirectory() as directory:
            outer = LocalFiles(directory)
            outer.provider = SimpleNamespace(remote_storage=True)
            self.assertEqual(DocumentPolicy.for_provider(outer), DocumentPolicy(False, False))
            with self.assertRaises(PermissionError):
                DocumentResource.publish(outer, 'Denied.md', b'private', max_bytes=100)
            self.assertFalse((Path(directory) / 'Denied.md').exists())
            outer.provider.provider = outer
            self.assertFalse(DocumentPolicy.for_provider(outer).writable)

    def test_notes_creation_uses_exclusive_verified_publication(self):
        with TemporaryDirectory() as directory:
            provider = LocalFiles(directory)
            notes = NotesLibrary(provider)
            self.assertEqual(notes.create('New note'), 'New note.md')
            with self.assertRaises((ValueError, FileExistsError)):
                notes.create('New note')
            with self.assertRaises(Exception):
                notes.create('Cancelled', cancelled=lambda: True)
            self.assertEqual(list(Path(directory).iterdir()), [Path(directory) / 'New note.md'])

    def test_streamed_metadata_rejects_remote_before_running_writer(self):
        source = SimpleNamespace(remote_storage=True, replace_stream=Mock())
        writer = Mock()
        with self.assertRaises(PermissionError):
            publish_document_stream(source, 'book.epub', writer, expected_revision='old')
        writer.assert_not_called()
        source.replace_stream.assert_not_called()

    def test_notes_folder_mutations_preserve_exclusivity_cancellation_and_remote_policy(self):
        from services.documents.storage import create_document_folder, move_document_resource
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'Vault').mkdir()
            provider = LocalFiles(root)
            notes = NotesLibrary(provider, 'Vault')
            self.assertEqual(notes.create_folder('Nested'), 'Vault/Nested')
            source = notes.create('Original')
            destination = 'Vault/Nested/Renamed.md'
            self.assertEqual(notes.move(source, destination), destination)
            self.assertFalse((root / source).exists())
            self.assertEqual((root / destination).read_bytes(), b'')
            other = notes.create('Other')
            with self.assertRaises((ValueError, FileExistsError)):
                notes.move(other, destination)
            self.assertTrue((root / other).exists())
            with self.assertRaises(Exception):
                notes.create_folder('Cancelled', cancelled=lambda: True)
            self.assertFalse((root / 'Vault/Cancelled').exists())
            with self.assertRaises(Exception):
                notes.move(other, 'Vault/Cancelled.md', cancelled=lambda: True)
            self.assertTrue((root / other).exists())
            provider.provider = SimpleNamespace(remote_storage=True)
            with self.assertRaises(PermissionError):
                create_document_folder(provider, 'Denied')
            with self.assertRaises(PermissionError):
                move_document_resource(provider, other, 'Denied.md')
            self.assertFalse((root / 'Denied').exists())
            self.assertTrue((root / other).exists())
