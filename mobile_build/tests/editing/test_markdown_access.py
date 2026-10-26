"""Remote sources remain read-only across text adapters and library commands."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from commonUtils.runtime.resources.local import LocalFiles
from features.text_editor.access import can_write
from features.text_editor.notes import NotesLibrary
from features.text_editor.resources import LocalTextCopies


class MarkdownAccessTests(unittest.TestCase):
    def test_private_local_is_editable_but_nested_remote_and_read_only_are_not(self):
        self.assertTrue(can_write(provider=SimpleNamespace(private=True)))
        remote = SimpleNamespace(remote_storage=True)
        self.assertFalse(can_write(provider=SimpleNamespace(provider=remote)))
        self.assertFalse(can_write(reader=SimpleNamespace(read_only=True)))
        self.assertFalse(can_write(provider=SimpleNamespace(capabilities=SimpleNamespace(replace=False))))
        remote.provider = remote
        self.assertFalse(can_write(provider=remote))

    def test_local_text_adapter_rejects_a_remote_even_if_it_exposes_local_writes(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'Note.md'
            path.write_bytes(b'# Original\r\n')
            provider = LocalFiles(directory)
            copies = LocalTextCopies(provider)
            reader = copies.open('Note.md')
            self.assertFalse(reader.read_only)
            self.assertTrue(NotesLibrary(provider).writable)
            provider.remote_storage = True
            self.assertFalse(NotesLibrary(provider).writable)
            self.assertTrue(copies.open('Note.md').read_only)
            with self.assertRaisesRegex(PermissionError, 'read-only'):
                copies.save(reader, '# Must not write')
            self.assertEqual(path.read_bytes(), b'# Original\r\n')

    def test_local_save_still_preserves_untouched_bytes(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'Note.md'
            original = b'\xef\xbb\xbf# Original\r\n\r\nText\n'
            path.write_bytes(original)
            copies = LocalTextCopies(LocalFiles(directory))
            reader = copies.open('Note.md')
            copies.save(reader, reader.text)
            self.assertEqual(path.read_bytes(), original)
