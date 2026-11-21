"""File/folder references survive browser and editor renames with this crypt mode."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.testing.stages import TestStage
from tests.resources.rename_cases import RenameCase

TEST_STAGE = TestStage.EXTENDED


class CryptRenameTests(RenameCase):
    def test_browser_file_folder_collision_and_references(self):
        self.crypt_renames('off', True, notes=False)

    def test_notes_file_folder_collision_references_and_save(self):
        self.crypt_renames('off', True, notes=True)
