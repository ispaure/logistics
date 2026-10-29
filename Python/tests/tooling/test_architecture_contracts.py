"""Prevent new architectural edges without importing production presentation."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from Scripts.architecture import ROOT, check, feature_edges, portable_sources, references


class ArchitectureTests(unittest.TestCase):
    def test_packaged_asset_names_do_not_hide_real_module_references(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / 'features/example'
            (folder / 'assets').mkdir(parents=True)
            (folder / 'assets/desktop.js').write_text('/* packaged presentation */')
            path = folder / 'canvas.py'
            path.write_text("from .assets import asset as load_asset\n"
                            "SCRIPT = load_asset('desktop.js')\n"
                            "FACTORY = 'desktop.dialogs:prompt'\n"
                            "MISSING = load_asset('mobile.module')\n")
            found = references(path, root)
            self.assertNotIn('desktop.js', found)
            self.assertIn('desktop.dialogs', found)
            self.assertIn('mobile.module', found)

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

    def test_portable_package_includes_new_nested_modules_and_deduplicates(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / 'Python/features/books/core'
            folder.mkdir(parents=True)
            (folder / '__init__.py').write_text('')
            (folder / 'nested').mkdir()
            module = folder / 'nested/data.py'
            module.write_text("FACTORY = 'toga:Box'\n")
            policy = {'portable_modules': ['features.books.core.nested.data'],
                      'portable_packages': ['features.books.core']}
            self.assertEqual(list(portable_sources(root, policy)),
                             ['features.books.core', 'features.books.core.nested.data'])
            (root / 'Scripts').mkdir()
            import json
            (root / 'Scripts/architecture.json').write_text(json.dumps(
                dict(policy, host_adapters=[], feature_dependencies=[])))
            from contextlib import redirect_stdout
            from io import StringIO
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(check(root), 1)
            self.assertIn('imports presentation: toga', output.getvalue())

    def test_portable_scope_rejects_missing_malformed_and_linked_sources(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ('missing.module', '../outside'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    portable_sources(root, {'portable_modules': [name]})
            folder = root / 'Python/features/books'
            folder.mkdir(parents=True)
            outside = root / 'outside.py'
            outside.write_text('')
            (folder / 'linked.py').symlink_to(outside)
            with self.assertRaisesRegex(ValueError, 'cannot traverse links'):
                portable_sources(root, {'portable_modules': ['features.books.linked']})
            with self.assertRaisesRegex(ValueError, 'cannot traverse links'):
                portable_sources(root, {'portable_packages': ['features.books']})

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

    def test_workflow_owners_include_their_specialist_regressions(self):
        from Scripts.ownership import selected_tests
        required = {
            'archives': [('desktop', 'test_archive_credentials.py'), ('desktop', 'test_archive_workspace_ui.py')],
            'books': [('mobile', 'test_reading_publication.py')],
            'comics': [('mobile', 'test_comic_sharing.py')],
            'lm': [('mobile', 'test_chat_inventory.py')],
            'pdf': [('mobile', 'test_pdf_reader.py')],
            'rclone': [
                ('desktop', 'test_remote_browser.py'),
                ('desktop', 'test_transfer_adapters.py'),
                ('desktop', 'test_transfer_service.py'),
                ('desktop', 'test_remote_bridge_native.py'),
                ('mobile', 'test_credential_document_lists.py'),
                ('mobile', 'test_native_credential_service.py'),
                ('mobile', 'test_native_transfer_service.py'),
                ('mobile', 'test_home_unlock.py'),
                ('mobile', 'test_connection_packages.py'),
                ('mobile', 'test_remote_service.py'),
            ],
            'text_editor': [('desktop', 'test_editor_resource_picker.py'), ('mobile', 'test_provider_opening.py')],
            'mobile-host': [('mobile', 'test_application_lifecycle.py')],
            'mobile-storage': [('mobile', 'test_storage_location.py')],
        }
        for owner, tests in required.items():
            with self.subTest(owner=owner):
                selection = selected_tests(ROOT, owner)
                self.assertTrue(set(tests) <= set(selection))
                self.assertEqual(len(selection), len(set(selection)))

    def test_invalid_suite_is_rejected_instead_of_selecting_mobile_tests(self):
        from unittest.mock import patch
        from Scripts.ownership import selected_tests
        with patch('Scripts.ownership.owners', return_value={'owner': {'tests': {'typo': ['test_*.py']}}}):
            with self.assertRaisesRegex(ValueError, 'unknown test suite'):
                selected_tests(ROOT, 'owner')


class CompatibilityTests(unittest.TestCase):
    def test_no_legacy_forwarding_modules_remain(self):
        from Scripts.compatibility import inventory
        rows = list(inventory(ROOT))
        self.assertEqual(rows, [])
