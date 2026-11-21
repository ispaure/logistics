"""The disposable sleep/trim driver cannot target a physical device."""

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
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from mobile_build.validation.reader_resume_tools import check


class ReaderResumeDriverTests(unittest.TestCase):
    def test_physical_device_is_rejected_before_any_adb_command_or_output(self):
        with TemporaryDirectory() as directory, patch('mobile_build.validation.reader_resume_tools.subprocess.run') as run:
            output = Path(directory) / 'evidence'
            with self.assertRaisesRegex(ValueError, 'explicit Android emulator'):
                check(Path('/tools/adb'), 'physical-device', output)
            run.assert_not_called()
            self.assertFalse(output.exists())
