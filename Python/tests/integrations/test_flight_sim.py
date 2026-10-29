"""Preference updates preserve originals when settings or preset files are invalid."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
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

    def test_failed_window_publication_restores_graphics_and_keeps_recovery(self):
        with TemporaryDirectory() as directory:
            path, window, preset = [Path(directory) / name for name in ('prefs', 'window', 'preset')]
            keys = ('renopt_SSAO_04', 'renopt_FSR_04', 'renopt_MSAA', 'renopt_draw_3d_04', 'renopt_draw_distance04', 'renopt_shadow_quality_04', 'renopt_vegetation_quality_04')
            original = ''.join(f'{key} 1\r\n' for key in keys).encode()
            path.write_bytes(original); window.write_bytes(b'old window'); preset.write_bytes(b'new window')
            publish = actions._publish_preferences
            def failing_window(target, old, new):
                if target == window:
                    raise OSError('window publication failed')
                return publish(target, old, new)
            with patch.object(actions.detection, 'get_xp12_preferences_path', return_value=path), patch.object(actions.detection, 'get_xp12_window_positions_path', return_value=window), patch.object(actions, '_publish_preferences', side_effect=failing_window):
                with self.assertRaises(OSError):
                    actions.set_all_xp12_settings(preset, 2, 2, 2, 2, 2, 2, 2)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(window.read_bytes(), b'old window')
            self.assertEqual(next(path.parent.glob('prefs.previous-*')).read_bytes(), original)
