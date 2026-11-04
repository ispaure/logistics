"""Project registration and comic behavior without shared-browser format switches."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import zipfile

from commonUtils.filesystem.directories import Directory
from commonUtils.filesystem.files import File
from commonUtils.formats.registry import file_from_path
from features.comics import register_file_types
from features.comics.cbz import CBZFile


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

    def test_cbz_contributes_metadata_and_declares_ui_elsewhere(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / 'comic.cbz'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('ComicInfo.xml', '<ComicInfo><Series>Example</Series><Writer>Author</Writer></ComicInfo>')
            comic = CBZFile(path)
            panel = comic.browser_panels()[0]
            self.assertEqual(panel.title, 'Comic Metadata')
            details = panel.load()
            self.assertIn(('Series', 'Example'), details.fields)
            self.assertIn(('Author', 'Author'), details.fields)
            self.assertIsNotNone(details.payload)
            # Browser actions/activation now live in the unified declaration;
            # a plain commonUtils browser can use CBZ panels without UI handlers.
            self.assertFalse(comic.browser_actions(None))
            self.assertFalse(comic.browser_activate(None))
            from features.application import registry
            definition = registry.get_feature_definition('comics')
            self.assertEqual([action.id for action in definition.browser.actions], ['edit_metadata', 'compress', 'encrypt'])
            self.assertEqual(len(definition.browser.activation), 1)
