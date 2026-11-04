"""Real crypt batching contracts across alternate filename/directory modes."""
import unittest
from commonUtils.testing.stages import TestStage
from tests.resources.localcrypt_batch_cases import LocalCryptBatchChecks

TEST_STAGE = TestStage.EXTENDED


class CryptBatchModeTests(LocalCryptBatchChecks, unittest.TestCase):
    def test_dataview_discovery_batches_names_across_folders(self):
        self.check_dataview_discovery_batches_names_across_folders({'directory_name_encryption': 'false'})

    def test_notes_link_lookup_shares_ciphertext_scan_and_bounded_fallback(self):
        self.check_notes_link_lookup_shares_ciphertext_scan_and_bounded_fallback({'directory_name_encryption': 'false'})
