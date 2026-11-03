"""Library mutations preserve visits rather than deduplicating filenames."""
import unittest
from commonUtils.testing.stages import TestStage
from features.notes_library.navigation import PathChange

TEST_STAGE = TestStage.REGRESSION


class NavigationTests(unittest.TestCase):
    def test_move_preserves_occurrences_cursor_and_path_boundaries(self):
        change = PathChange('a', 'moved')
        self.assertEqual(change.history(['a/x', 'ab/x', 'a/x'], 2),
                         (['moved/x', 'ab/x', 'moved/x'], 2))
        self.assertEqual(change.positions({'a/x': 12, 'ab/x': 7}),
                         {'moved/x': 12, 'ab/x': 7})
        self.assertIsNone(change.remap(None))

    def test_delete_preserves_current_occurrence_and_forward_branch(self):
        change = PathChange(deleted='a')
        self.assertEqual(change.history(['b', 'a/x', 'b', 'c'], 2), (['b', 'b', 'c'], 1))
        self.assertEqual(change.history(['a/x', 'b'], -1), (['b'], -1))
        self.assertEqual(change.positions({'a/x': 12, 'ab/x': 7}), {'ab/x': 7})
        self.assertFalse(change.removes(None))


if __name__ == '__main__':
    unittest.main()
