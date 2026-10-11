import unittest
from unittest.mock import patch, Mock
from pathlib import Path
from tempfile import TemporaryDirectory
from features.system_tools import actions
from commonUtils.runtime.platform import OS


class SystemToolsTests(unittest.TestCase):
    def test_invalid_drive_never_launches_repair(self):
        with patch.object(actions, 'get_os', return_value=OS.WIN), patch.object(actions, 'effective_settings') as ini, patch.object(actions.cmdShellWrapper, 'exec_cmd') as execute:
            ini.return_value.get.return_value = 'D: & echo unsafe'
            with self.assertRaises(ValueError):
                actions.run_repair_ntfs_on_d()
            execute.assert_not_called()

    def test_restore_uses_recorded_battery_values(self):
        with TemporaryDirectory() as folder:
            preferences = Path(folder) / 'features.json'
            preferences.with_name('battery-power.json').write_text('{"sleep": 7, "disablesleep": 0}')
            with patch.object(actions, 'get_os', return_value=OS.MAC), patch.object(actions, 'preferences_path', return_value=preferences), patch.object(actions.cmdShellWrapper, 'exec_cmd', return_value=True) as execute:
                self.assertTrue(actions.enable_macos_lid_sleep())
                execute.assert_called_once_with('sudo pmset -b sleep 7 && sudo pmset -b disablesleep 0', in_new_window=True)

    def test_disable_records_battery_sleep_and_separate_global_sleep_flag(self):
        with TemporaryDirectory() as folder:
            preferences = Path(folder) / 'features.json'
            custom = Mock(success=True, stdout=['Battery Power:', ' sleep 7', 'AC Power:', ' sleep 20'])
            general = Mock(success=True, stdout=['System-wide power settings:', ' SleepDisabled 0'])
            with patch.object(actions, 'get_os', return_value=OS.MAC), patch.object(actions, 'preferences_path', return_value=preferences), patch.object(actions.cmdShellWrapper, 'run_command', side_effect=[custom, general]), patch.object(actions.cmdShellWrapper, 'exec_cmd', return_value=True):
                self.assertTrue(actions.disable_macos_lid_sleep())
            import json
            self.assertEqual(json.loads(preferences.with_name('battery-power.json').read_text()), {'sleep': 7, 'disablesleep': 0})
