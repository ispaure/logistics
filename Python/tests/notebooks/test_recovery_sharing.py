"""Checkpoint history retains immutable native ink once, not once per edit."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from features.notebooks.editor import Editor
from features.notebooks.notebook import Notebook
from features.notebooks.recovery import Repository
from features.notebooks._vendor.rmscene import scene_stream as ss


class RecoverySharingTests(unittest.TestCase):
    def test_long_history_shares_points_and_survives_undo_redo_and_reopen(self):
        with TemporaryDirectory() as directory:
            book = Notebook.new('Checkpoint sharing')
            for _ in range(3):
                book.add_page()
            repository = Repository(Path(directory))
            key = repository.create(book)
            editor = Editor(book, lambda value: repository.save(key, value))
            for index in range(60):
                editor.apply(dict(op='page', index=index % 4))
                editor.apply(dict(op='stroke', tool=15, color=6, width=2,
                    points=[[100 + j, 200 + index, .2 + .7 * j / 31] for j in range(32)]))
            pages = book.pages + [page for snapshot in editor.undo for page in snapshot[0]]
            strokes = {id(stroke) for page in pages for stroke in page.ink.strokes}
            blocks = {id(block) for page in pages for block in page.ink._blocks
                      if isinstance(block, ss.SceneLineItemBlock) and not block.item.deleted_length}
            self.assertEqual(len(strokes), 60)
            self.assertEqual(len(blocks), 60)
            expected = [book.page(i).to_bytes() for i in range(4)]
            for _ in range(50):
                editor.apply(dict(op='undo'))
            self.assertEqual(sum(len(book.page(i).strokes) for i in range(4)), 10)
            for _ in range(50):
                editor.apply(dict(op='redo'))
            self.assertEqual([book.page(i).to_bytes() for i in range(4)], expected)
            reopened = repository.open(key)
            self.assertEqual([reopened.page(i).to_bytes() for i in range(4)], expected)
            # Moving a shared native stroke must leave the Undo version intact.
            editor.apply(dict(op='page', index=0))
            original = book.page(0).strokes[0]
            original_payload = deepcopy(original.payload())
            editor.apply(dict(op='transform', ids=[original.id], dx=5, dy=7))
            self.assertEqual(original.payload(), original_payload)
            self.assertIsNot(book.page(0).strokes[0], original)
            editor.apply(dict(op='undo'))
            self.assertEqual(book.page(0).strokes[0].payload(), original_payload)


if __name__ == '__main__':
    unittest.main()
