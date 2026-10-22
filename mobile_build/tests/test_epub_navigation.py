"""Nested chapter disclosure preserves exact destinations without search UI."""
from types import SimpleNamespace
import unittest
import toga
from features.books.mobile.navigation import ChapterList


class ChapterNavigationTests(unittest.TestCase):
    def test_nested_disclosure_and_fragment_activation(self):
        entries = [SimpleNamespace(label=label, depth=depth, index=index, fragment=fragment)
            for label, depth, index, fragment in [('Part', 0, 0, ''), ('Section', 1, 0, 'section'),
                ('Deep note', 2, 0, 'deep'), ('Next', 0, 1, '')]]
        selected = []
        chapters = ChapterList(entries, selected.append)
        self.assertEqual(len(chapters.rows.children), 4)
        chapters.rows.children[0].children[1].on_press()
        self.assertEqual(len(chapters.rows.children), 2)
        chapters.rows.children[0].children[1].on_press()
        self.assertEqual(len(chapters.rows.children), 4)
        chapters.rows.children[1].children[-1].on_press()
        self.assertIs(selected[0], entries[1])
        def descendants(widget):
            return [widget] + [child for item in widget.children for child in descendants(item)]
        self.assertFalse(any(isinstance(w, (toga.TextInput, toga.Selection)) for w in descendants(chapters.rows)))
