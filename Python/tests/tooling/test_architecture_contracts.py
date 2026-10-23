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
            path.write_text("from ..comics import pages\nFACTORY = 'desktop.dialogs.prompt'\n")
            found = references(path, root)
            self.assertIn('features.comics.pages', found)
            self.assertIn('desktop.dialogs.prompt', found)

    def test_colon_qualified_factories_expose_their_module_dependencies(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / 'Python/features/books'
            folder.mkdir(parents=True)
            path = folder / 'example.py'
            path.write_text("TYPE = 'features.comics.cbz:CBZFile'\n"
                            "PROMPT = 'desktop.dialogs:prompt'\n"
                            "TEXT = 'Use features.other.Type for examples'\n"
                            "INVALID = 'features.invalid:Not a name'\n")
            found = references(path, root / 'Python')
            self.assertIn('features.comics.cbz', found)
            self.assertIn('desktop.dialogs', found)
            self.assertNotIn('features.invalid', found)
            self.assertEqual(feature_edges(root), (
                {('Python/features/books/example.py', 'desktop.dialogs')}, {('books', 'comics')}))

    def test_portable_contract_rejects_deferred_ui_dependencies(self):
        from contextlib import redirect_stdout
        from io import StringIO
        import json
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / 'Python/features/books'
            folder.mkdir(parents=True)
            (root / 'Scripts').mkdir()
            policy = {'host_adapters': [], 'feature_dependencies': [],
                      'portable_modules': ['features.books.data']}
            (root / 'Scripts/architecture.json').write_text(json.dumps(policy))
            for factory in ('commonUtils.ui.native.forms:FittedLabel', 'PySide6.QtWidgets:QWidget', 'toga'):
                with self.subTest(factory=factory):
                    (folder / 'data.py').write_text(f'FACTORY = {factory!r}\n')
                    output = StringIO()
                    with redirect_stdout(output):
                        self.assertEqual(check(root), 1)
                    self.assertIn('imports presentation', output.getvalue())

    def test_external_feature_link_is_not_scanned(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'Python/features/emulation').mkdir(parents=True)
            (root / 'Python/features/emulation/invalid.py').write_text('this is not Python!')
            self.assertEqual(feature_edges(root), (set(), set()))


class OwnershipTests(unittest.TestCase):
    def test_declared_sources_guides_manifests_and_test_groups_exist(self):
        from Scripts.ownership import owners, selected_tests
        for name, entry in owners().items():
            with self.subTest(owner=name):
                self.assertTrue((ROOT / entry['guide']).is_file())
                for source in entry['sources']:
                    self.assertTrue((ROOT / source).exists())
                if 'mobile_manifest' in entry:
                    self.assertTrue((ROOT / entry['mobile_manifest']).is_file())
                self.assertTrue(selected_tests(ROOT, name))

    def test_unknown_owner_is_a_failure(self):
        from Scripts.ownership import selected_tests
        with self.assertRaisesRegex(ValueError, 'Unknown owner'):
            selected_tests(ROOT, 'not-a-real-owner')


class CompatibilityTests(unittest.TestCase):
    def test_no_legacy_forwarding_modules_remain(self):
        from Scripts.compatibility import inventory
        rows = list(inventory(ROOT))
        self.assertEqual(rows, [])
