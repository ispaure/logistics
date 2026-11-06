"""Only reviewed, unchanged, byte-identical copies may be deleted."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from commonUtils.runtime.streams import file_sha256
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

    def test_original_changed_after_review_preserves_both_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / 'note.txt'
            copy = root / 'note (user conflicted copy 2026).txt'
            original.write_bytes(b'original')
            copy.write_bytes(b'original')
            review = review_conflicts(root)
            self.assertTrue(review[0].identical)
            original.write_bytes(b'edited after review')
            result = delete_reviewed_conflicts(review)
            self.assertEqual(len(result.failed), 1)
            self.assertEqual(len(result.completed), 0)
            self.assertEqual(original.read_bytes(), b'edited after review')
            self.assertEqual(copy.read_bytes(), b'original')

    def test_edits_and_replacements_after_hash_preserve_both_files(self):
        for changed_name in ('note.txt', 'note (user conflicted copy 2026).txt'):
            for replace in (False, True):
                with self.subTest(changed=changed_name, replace=replace), TemporaryDirectory() as directory:
                    root = Path(directory).resolve()
                    original = root / 'note.txt'
                    copy = root / 'note (user conflicted copy 2026).txt'
                    original.write_bytes(b'original')
                    copy.write_bytes(b'original')
                    review = review_conflicts(root)
                    self.assertTrue(review[0].identical)
                    changed = root / changed_name

                    def hash_then_change(path):
                        digest = file_sha256(path)
                        if path == changed:
                            if replace:
                                replacement = root / 'replacement.tmp'
                                replacement.write_bytes(b'changed after hash')
                                replacement.replace(path)
                            else:
                                path.write_bytes(b'changed after hash')
                        return digest

                    with patch('features.dropbox.conflicts.file_sha256', side_effect=hash_then_change):
                        result = delete_reviewed_conflicts(review)
                    self.assertEqual(len(result.failed), 1)
                    self.assertEqual(len(result.completed), 0)
                    self.assertEqual(changed.read_bytes(), b'changed after hash')
                    unchanged = original if changed == copy else copy
                    self.assertEqual(unchanged.read_bytes(), b'original')

    def test_cancellation_during_apply_finishes_current_item(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            original = root / 'note.txt'
            original.write_bytes(b'original')
            for name in ('user1', 'user2'):
                (root / f'note ({name} conflicted copy 2026).txt').write_bytes(b'original')
            first, second = review_conflicts(root)
            cancelled = False

            def hash_and_cancel(path):
                nonlocal cancelled
                cancelled = True
                return file_sha256(path)

            with patch('features.dropbox.conflicts.file_sha256', side_effect=hash_and_cancel):
                result = delete_reviewed_conflicts((first, second), cancelled=lambda: cancelled)
            self.assertTrue(result.cancelled)
            self.assertEqual(result.completed, [first])
            self.assertEqual(result.remaining, [second])
            self.assertEqual(result.failed, {})
            self.assertFalse(first.path.exists())
            self.assertEqual(second.path.read_bytes(), b'original')
