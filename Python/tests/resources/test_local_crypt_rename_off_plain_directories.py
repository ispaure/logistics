"""File/folder references survive browser and editor renames with this crypt mode."""
from commonUtils.testing.stages import TestStage
from tests.resources.rename_cases import RenameCase

TEST_STAGE = TestStage.EXTENDED


class CryptRenameTests(RenameCase):
    def test_browser_file_folder_collision_and_references(self):
        self.crypt_renames('off', False, notes=False)

    def test_notes_file_folder_collision_references_and_save(self):
        self.crypt_renames('off', False, notes=True)
