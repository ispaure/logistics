"""Behavioral regressions owned by this feature."""
import unittest
from commonUtils.testing.stages import TestStage
from unittest.mock import patch

TEST_STAGE = TestStage.REGRESSION


class FolderEntryIdentityTests(unittest.TestCase):
    def test_duplicate_local_names_are_preserved_and_remote_match_is_explicit(self):
        from models.local_folder import LocalFolder
        from services.folders.entries import get_folder_entries
        folders = [LocalFolder('/first/Books'), LocalFolder('/second/Books')]
        with patch('services.folders.entries._get_excluded_remote_names', return_value=set()), patch('services.folders.entries._get_excluded_folder_name_suffixes', return_value=()):
            entries = get_folder_entries(local_folders=folders)
            self.assertEqual({entry.local.path for entry in entries}, {folder.path for folder in folders})
            with self.assertRaises(ValueError):
                get_folder_entries(['Books'], local_folders=folders)
