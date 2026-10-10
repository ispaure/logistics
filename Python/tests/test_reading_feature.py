"""One presented feature, atomic engine toggles and deduplicated metadata actions."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import Mock, patch
from books_fixture import make_book
from commonUtils.ui import pyside as qt
from commonUtils.features import Feature, ActionContext
from features import books, comics, images, registry
from features.books.file_type import EPUBFile
from features.comics.cbz import CBZFile


class ReadingFeatureTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def engines(self):
        owner = ModuleType('features.owner')
        child = ModuleType('features.child')
        dependency = ModuleType('features.dependency')
        owner.register = lambda: Feature(id='owner', label='Reading')
        child.register = lambda: Feature(id='child', requires=('dependency',))
        dependency.register = lambda: Feature(id='dependency')
        child.FEATURE_GROUP = 'owner'
        return owner, child, dependency

    def test_group_has_one_state_and_toggles_all_engines_with_dependencies(self):
        engines = self.engines()
        with patch.object(registry, 'load_features', return_value=list(engines)), \
             patch.object(registry, '_disabled_features', set()), patch.object(registry, '_initialized_features', set()):
            states = {state.name: state for state in registry.get_feature_states()}
            self.assertEqual(set(states), {'owner', 'dependency'})
            self.assertEqual(states['owner'].members, ('owner', 'child'))
            self.assertEqual(states['owner'].dependencies, ('dependency',))
            with self.assertRaisesRegex(ValueError, 'Reading'):
                registry.set_feature_enabled('dependency', False)
            registry.set_feature_enabled('owner', False)
            self.assertFalse(registry.is_feature_enabled('owner'))
            self.assertFalse(registry.is_feature_enabled('child'))
            registry.set_feature_enabled('dependency', False)
            registry.set_feature_enabled('child', True)  # Legacy engine entry point.
            self.assertTrue(all(registry.is_feature_enabled(name) for name in ('owner', 'child', 'dependency')))

    def test_failed_group_enable_rolls_back_both_engines(self):
        engines = self.engines()
        engines[1].register = lambda: Feature(id='child', initialize=Mock(side_effect=RuntimeError('Cannot initialize')))
        with patch.object(registry, 'load_features', return_value=list(engines)), \
             patch.object(registry, '_disabled_features', {'owner', 'child'}), patch.object(registry, '_initialized_features', set()):
            with self.assertRaisesRegex(RuntimeError, 'Cannot initialize'):
                registry.set_feature_enabled('owner', True)
            self.assertEqual(registry._disabled_features, {'owner', 'child'})

    def test_real_feature_is_one_settings_entry_and_keeps_legacy_definitions(self):
        with patch.object(registry, 'load_features', return_value=[books, comics, images]):
            states = {state.name: state for state in registry.get_feature_states()}
            self.assertNotIn('comics', states)
            self.assertEqual(states['books'].label, 'Books & Comics')
            self.assertEqual(states['books'].members, ('books', 'comics'))
            self.assertEqual(registry.get_feature_definition('comics').id, 'comics')
            self.assertEqual(registry.get_feature_definition('books').id, 'books')
            self.assertEqual(registry.get_pages(), [])

    def test_mixed_selection_has_one_metadata_key_and_routes_to_both_editors(self):
        from commonUtils.ui.file_browser.extensions import InstalledFeature
        from features.books.controller import BooksController
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            epub = EPUBFile(make_book(root / 'book.epub'))
            cbz = CBZFile(root / 'comic.cbz')
            browser = qt.QWidget()
            browser.install_extension = Mock()
            self.addCleanup(browser.deleteLater)
            book_controller = BooksController(browser)
            comic_controller = SimpleNamespace(_open_editor=Mock(), _notify_idle=Mock())
            bindings = [InstalledFeature(books.register(), browser, host=browser, controller=book_controller),
                        InstalledFeature(comics.register(), browser, host=browser, controller=comic_controller)]
            context = SimpleNamespace(selection=(epub, cbz))
            actions = {action.key: action for binding in bindings for item in context.selection
                       for action in binding._actions_for(item, context)}
            metadata = [action for action in actions.values() if action.title == 'Edit metadata…']
            self.assertEqual(len(metadata), 1)
            from features.books.metadata_actions import edit_metadata
            with patch.object(book_controller, 'open') as open_epub, \
                 patch('features.registry.get_feature_definition', return_value=SimpleNamespace(
                     install_browser=lambda *a, **k: SimpleNamespace(controller=comic_controller))):
                edit_metadata(ActionContext(browser, browser, book_controller, (epub, cbz)))
            open_epub.assert_called_once_with(epub.path, edit=True)
            comic_controller._open_editor.assert_called_once_with((cbz.path,))
