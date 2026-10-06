"""Project registration and comic behavior without shared-browser format switches."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import zipfile

from commonUtils.dirUtils import Directory
from commonUtils.fileUtils import File
from commonUtils.fileTypes.registry import file_from_path
from features.comics import register_file_types
from features.comics.cbz import CBZFile
from features.comics.browser_support import directory_actions


class ComicFileTypeTests(unittest.TestCase):
    def test_registered_types_apply_to_directory_listing_without_loading_xml(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'example.CBZ').write_bytes(b'not yet a valid archive')
            directory = Directory(root)
            register_file_types()
            with patch('features.comics.library.ComicDocument', side_effect=AssertionError('listing must not parse metadata')):
                self.assertIsInstance(directory.list_files()[0], CBZFile)
                self.assertIsInstance(file_from_path(root / 'example.CBZ'), CBZFile)
                self.assertIs(type(File(root / 'example.CBZ')), File)

    def test_cbz_contributes_metadata_and_selection_actions(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / 'comic.cbz'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('ComicInfo.xml', '<ComicInfo><Series>Example</Series><Writer>Author</Writer></ComicInfo>')
            comic = CBZFile(path)
            panel = comic.browser_panels()[0]
            self.assertEqual(panel.title, 'Comic Metadata')
            self.assertTrue(panel.default_enabled)
            details = panel.load()
            self.assertIn(('Series', 'Example'), details.fields)
            self.assertIn(('Author', 'Author'), details.fields)
            self.assertIsNotNone(details.payload)
            calls = []
            directory = Directory(root)
            context = SimpleNamespace(selection=(comic, directory, File(root / 'other.txt')),
                                      invoke=lambda *args: calls.append(args))
            comic.browser_actions(context)[0].run(context)
            self.assertEqual(calls[-1], ('comics.edit_metadata', [path, root]))
            self.assertTrue(comic.browser_activate(context))
            self.assertEqual(calls[-1], ('comics.read', path))
            directory_actions(directory, context)[0].run(context)
            self.assertEqual(calls[-1], ('comics.edit_metadata', [path, root]))
            self.assertFalse(directory_actions(File(root / 'other.txt'), context))

    def test_feature_file_registration_precedes_all_initializers(self):
        from features import registry
        events = []
        features = [SimpleNamespace(__name__='early', initialize=lambda: events.append('initialize early')),
                    SimpleNamespace(__name__='later', register_file_types=lambda: events.append('register later'),
                                    initialize=lambda: events.append('initialize later'))]
        with patch.object(registry, '_log_unavailable_features'), patch.object(registry, 'get_available_features', return_value=features):
            registry.initialize_features()
        self.assertEqual(events, ['register later', 'initialize early', 'initialize later'])
