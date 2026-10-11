"""Preference updates preserve originals when settings or preset files are invalid."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from features.flight_sim import actions


class PreferenceTests(unittest.TestCase):
    def test_missing_key_does_not_change_file(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'prefs'; original = b'unrelated 2\r\n'
            path.write_bytes(original)
            with patch.object(actions.detection, 'get_xp12_preferences_path', return_value=path):
                with self.assertRaisesRegex(ValueError, 'missing'):
                    actions.set_xp12_fsr_setting(3)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_update_preserves_bom_endings_and_backup(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'prefs'; original = b'\xef\xbb\xbfrenopt_FSR_04 1\r\nother 2\r\n'
            path.write_bytes(original)
            with patch.object(actions.detection, 'get_xp12_preferences_path', return_value=path):
                actions.set_xp12_fsr_setting(3)
            self.assertEqual(path.read_bytes(), original.replace(b'04 1', b'04 3'))
            self.assertEqual(next(path.parent.glob('*.previous-*')).read_bytes(), original)

    def test_external_edit_is_preserved(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'prefs'; path.write_bytes(b'external')
            with self.assertRaisesRegex(RuntimeError, 'outside'):
                actions._publish_preferences(path, b'original', b'updated')
            self.assertEqual(path.read_bytes(), b'external')
