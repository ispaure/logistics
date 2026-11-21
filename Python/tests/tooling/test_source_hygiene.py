"""Secret checks identify categories without returning sensitive matched data."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import unittest
from Scripts.hygiene import categories


class HygieneTests(unittest.TestCase):
    def test_private_key_and_provider_shapes_are_detected(self):
        self.assertEqual(categories(b'-----BEGIN ' + b'PRIVATE KEY-----'), ['private key'])
        self.assertEqual(categories(b'ghp_' + b'A' * 36), ['GitHub token'])
        self.assertEqual(categories(b'AKIA' + b'A' * 16), ['AWS access key'])
        self.assertEqual(categories(b'API_KEY = os.environ["API_KEY"]'), [])
