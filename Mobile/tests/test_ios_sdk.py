import unittest
from Mobile.select_ios_sdk import choose, version


class AppleSDKTests(unittest.TestCase):
    def test_older_build_cannot_claim_duo_opt_in(self):
        with self.assertRaises(RuntimeError):
            choose([('/old', '26.5'), ('/partial', '27.0')])
        self.assertEqual(choose([('/old', '26.5'), ('/duo', '27.1')]), ('/duo', '27.1'))

    def test_sdk_selection_handles_patch_versions_and_invalid_metadata(self):
        self.assertEqual(choose([('/patch', '27.1.1'), ('/duo', '27.1')]), ('/patch', '27.1.1'))
        with self.assertRaises(ValueError):
            version('unknown')
