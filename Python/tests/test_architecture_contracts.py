"""Prevent new architectural edges without importing production presentation."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from Scripts.architecture import ROOT, check, feature_edges, references


class ArchitectureTests(unittest.TestCase):
    def test_current_tree_obeys_reviewed_boundaries(self):
        self.assertEqual(check(ROOT), 0)

    def test_relative_imports_and_lazy_factories_are_visible(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / 'features/books'
            folder.mkdir(parents=True)
            path = folder / 'example.py'
            path.write_text("from ..comics import pages\nFACTORY = 'ui_new.dialogs.prompt'\n")
            found = references(path, root)
            self.assertIn('features.comics.pages', found)
            self.assertIn('ui_new.dialogs.prompt', found)

    def test_external_feature_link_is_not_scanned(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'Python/features/emulation').mkdir(parents=True)
            (root / 'Python/features/emulation/invalid.py').write_text('this is not Python!')
            self.assertEqual(feature_edges(root), (set(), set()))
