"""The disposable sleep/trim driver cannot target a physical device."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from Mobile.reader_resume_tools import check


class ReaderResumeDriverTests(unittest.TestCase):
    def test_physical_device_is_rejected_before_any_adb_command_or_output(self):
        with TemporaryDirectory() as directory, patch('Mobile.reader_resume_tools.subprocess.run') as run:
            output = Path(directory) / 'evidence'
            with self.assertRaisesRegex(ValueError, 'explicit Android emulator'):
                check(Path('/tools/adb'), 'physical-device', output)
            run.assert_not_called()
            self.assertFalse(output.exists())
