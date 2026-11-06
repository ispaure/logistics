"""Behavioral regressions owned by this feature."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.configuration.layered import register_settings
from commonUtils.testing.stages import TestStage
from mobile import folder_hub
from models.local_folder import LocalFolder
from services.folders.entries import get_folder_entries

TEST_STAGE = TestStage.REGRESSION


class FolderEntryIdentityTests(unittest.TestCase):
    def setUp(self):
        temporary = self.enterContext(TemporaryDirectory())
        settings = Path(temporary) / 'config.ini'
        settings.write_text('[Folders]\nexcluded_remote_names = Straße\n'
                            'excluded_folder_name_suffixes = -Hidden\n', encoding='utf-8')
        self.enterContext(patch('config.get_config_file_path', return_value=settings))

    def test_duplicate_local_names_are_preserved_and_remote_match_is_explicit(self):
        folders = [LocalFolder('/first/Books'), LocalFolder('/second/Books')]
        entries = get_folder_entries(local_folders=[*folders, LocalFolder(folders[0].path)])
        self.assertEqual([entry.local for entry in entries], folders)
        with self.assertRaisesRegex(ValueError, "Multiple local folders named 'Books'"):
            get_folder_entries(['Books'], local_folders=folders)

    def test_merge_preserves_exact_names_and_applies_side_specific_exclusions(self):
        books = LocalFolder('/first/Books')
        folders = [books, LocalFolder(books.path), LocalFolder('/first/STRASSE'),
                   LocalFolder('/first/Archive-HIDDEN'), LocalFolder('/first/Local')]
        names = [' Books ', 'Books', 'books', ' STRASSE ', 'Straße Annex',
                 'Remote-hidden', '', '   ', None, 0, 7]
        context = object()
        entries = get_folder_entries(names, 'provider', context, local_folders=iter(folders))
        self.assertEqual([(entry.name, entry.has_local, entry.remote_name) for entry in entries],
                         [('7', False, '7'), ('Books', True, 'Books'), ('Local', True, None),
                          ('STRASSE', True, None), ('Straße Annex', False, 'Straße Annex'),
                          ('books', False, 'books')])
        self.assertIs(entries[1].local, books)
        for entry in entries:
            self.assertEqual(entry.remote_source, 'provider' if entry.has_remote else None)
            self.assertIs(entry.remote_context, context if entry.has_remote else None)
        self.assertEqual(get_folder_entries(names, 'provider', context, False, folders),
                         [entry for entry in entries if entry.has_remote])

    def test_empty_local_name_is_retained_only_in_the_local_listing(self):
        root = LocalFolder(Path.cwd().anchor)
        entries = get_folder_entries(['', ' '], local_folders=[root])
        self.assertEqual([(entry.name, entry.local, entry.remote_name) for entry in entries],
                         [('', root, None)])
        self.assertEqual(get_folder_entries(['', ' '], include_local_only=False,
                                            local_folders=[root]), [])


class FolderEntryPolicyParityTests(unittest.TestCase):
    def test_mobile_and_desktop_follow_personal_folder_exclusions_and_reset(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = root / 'configFile.ini'
            settings.write_text('[Folders]\nexcluded_remote_names = Default\n'
                                'excluded_folder_name_suffixes = -Old\n')
            store = register_settings(settings, root / 'personal.ini')
            remotes = ['Default', 'Personal', 'Draft-OLD', 'Draft-New', 'Keep']
            overrides = {('Folders', 'excluded_remote_names'): 'personal',
                         ('Folders', 'excluded_folder_name_suffixes'): '-new'}

            with patch('config.get_config_file_path', return_value=settings), patch.object(
                folder_hub, '__file__', str(root / 'mobile/folder_hub.py')
            ):
                def check_visible(expected):
                    self.assertCountEqual(folder_hub.visible_remotes(remotes), expected)
                    self.assertCountEqual(
                        [entry.name for entry in get_folder_entries(remotes, local_folders=[])],
                        expected,
                    )

                check_visible(['Personal', 'Draft-New', 'Keep'])
                store.save(overrides)
                check_visible(['Default', 'Draft-OLD', 'Keep'])
                store.save(dict.fromkeys(overrides))
                check_visible(['Personal', 'Draft-New', 'Keep'])
