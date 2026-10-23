"""Only reviewed, unchanged, byte-identical copies may be deleted."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from features.dropbox.conflicts import review_conflicts, delete_reviewed_conflicts


class ConflictTests(unittest.TestCase):
    def test_unique_contents_and_changed_copies_are_preserved(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / 'note.txt'; original.write_bytes(b'original')
            copy = root / 'note (user conflicted copy 2026).txt'; copy.write_bytes(b'unique')
            review = review_conflicts(root)
            self.assertFalse(review[0].identical)
            delete_reviewed_conflicts(review)
            self.assertEqual(copy.read_bytes(), b'unique')
            copy.write_bytes(b'original')
            review = review_conflicts(root)
            self.assertTrue(review[0].identical)
            copy.write_bytes(b'changed')
            result = delete_reviewed_conflicts(review)
            self.assertEqual(len(result.failed), 1)
            self.assertEqual(copy.read_bytes(), b'changed')

    def test_reviewed_identical_copy_is_deleted_and_original_kept(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / 'note.txt'; original.write_bytes(b'original')
            copy = root / 'note (user conflicted copy 2026).txt'; copy.write_bytes(b'original')
            result = delete_reviewed_conflicts(review_conflicts(root))
            self.assertEqual([item.path for item in result.completed], [copy.resolve()])
            self.assertFalse(copy.exists())
            self.assertEqual(original.read_bytes(), b'original')
