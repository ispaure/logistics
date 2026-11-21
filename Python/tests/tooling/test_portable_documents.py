"""Enforce the document-core import boundary in a clean interpreter."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
import subprocess
import sys
import unittest


class PortableDocumentTests(unittest.TestCase):
    def test_core_without_desktop_and_image_packages(self):
        result = subprocess.run([sys.executable, str(Path(__file__).parents[1] / 'portable_documents.py')],
                                text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
