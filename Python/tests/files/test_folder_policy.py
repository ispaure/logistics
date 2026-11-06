"""Folder exclusions share layered settings while retaining legacy INI parsing."""

from configparser import DuplicateOptionError
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.configuration.layered import register_settings
from commonUtils.testing.stages import TestStage
from services.folders.policy import read_exclusions, visible_name

TEST_STAGE = TestStage.REGRESSION


class FolderPolicyTests(unittest.TestCase):
    def test_personal_exclusions_replace_defaults_until_reset(self):
        with TemporaryDirectory() as temporary:
            defaults = Path(temporary) / 'config.ini'
            defaults.write_text('[Folders]\nEXCLUDED_REMOTE_NAMES = Default, , Second\n'
                                'excluded_folder_name_suffixes = -OLD\n', encoding='utf-8-sig')
            store = register_settings(defaults, defaults.with_name('personal.ini'))
            packaged = (frozenset({'default', 'second'}), ('-old',))
            self.assertEqual(read_exclusions(defaults), packaged)

            overrides = {('Folders', 'excluded_remote_names'): 'Personal%, , Extra',
                         ('Folders', 'excluded_folder_name_suffixes'): '-PRIVATE, -TMP'}
            store.save(overrides)
            exclusions = read_exclusions(defaults)
            self.assertEqual(exclusions, (frozenset({'personal%', 'extra'}), ('-private', '-tmp')))
            self.assertFalse(visible_name('PERSONAL%', exclusions, remote=True))
            self.assertTrue(visible_name('PERSONAL%', exclusions))
            self.assertFalse(visible_name('Example-TMP', exclusions))

            store.save(dict.fromkeys(overrides))
            self.assertEqual(read_exclusions(defaults), packaged)

    def test_unregistered_mobile_payload_uses_packaged_defaults(self):
        from mobile import folder_hub

        source = Path(folder_hub.__file__).resolve().parents[1] / 'configFile.ini'
        with TemporaryDirectory() as temporary:
            payload = Path(temporary)
            packaged_config = payload / 'services/configFile.ini'
            packaged_config.parent.mkdir()
            packaged_config.write_bytes(source.read_bytes())
            with patch.object(folder_hub, '__file__', str(payload / 'mobile/folder_hub.py')):
                self.assertEqual(folder_hub.visible_remotes(
                    ['Dropbox', 'gDRIVE2', 'Archive-pmsdata', 'Library']), ['Library'])

    def test_case_only_duplicate_options_raise(self):
        with TemporaryDirectory() as temporary:
            defaults = Path(temporary) / 'config.ini'
            defaults.write_text('[Folders]\nexcluded_remote_names = First\nEXCLUDED_REMOTE_NAMES = Second\n')
            with self.assertRaises(DuplicateOptionError):
                read_exclusions(defaults)
