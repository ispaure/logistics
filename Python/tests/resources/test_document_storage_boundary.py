"""Format editing stays independent of concrete storage implementations."""
import ast
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from commonUtils.runtime.resources.local import LocalFiles
from features.text_editor.notes import NotesLibrary
from services.documents.storage import DocumentPolicy, DocumentResource, publish_document_stream


class DocumentBoundaryTests(unittest.TestCase):
    def test_editor_features_do_not_import_encryption_implementations(self):
        root = Path(__file__).resolve().parents[2] / 'features'
        paths = list((root / 'text_editor').rglob('*.py'))
        paths += [root / 'books/metadata.py', root / 'comics/library.py', root / 'notebooks/storage.py', root / 'notebooks/mobile/documents.py', root / 'comics/mobile/collection/workflows.py']
        for path in paths:
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                names = [node.module or ''] if isinstance(node, ast.ImportFrom) else (
                    [alias.name for alias in node.names] if isinstance(node, ast.Import) else [])
                self.assertFalse(any('localcrypt' in name or name.startswith('features.rclone') for name in names), str(path))

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
