import unittest
import base64
from unittest.mock import patch, Mock
from pathlib import Path
from tempfile import TemporaryDirectory
from features.system_tools import actions
from commonUtils.runtime.platform import OS


class SystemToolsTests(unittest.TestCase):
    def repair_payload(self, execute):
        execute.assert_called_once()
        launcher = execute.call_args.args[0]
        self.assertIn("Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -Verb RunAs", launcher)
        self.assertIn("'-NoProfile', '-NoExit', '-EncodedCommand'", launcher)
        self.assertNotIn('-Wait', launcher)
        encoded = launcher.split("'-EncodedCommand', '", 1)[1].split("'", 1)[0]
        return base64.b64decode(encoded, validate=True).decode('utf-16-le')

    def test_system_repair_preserves_commands_without_batch_files(self):
        with patch.object(actions, 'get_os', return_value=OS.WIN), patch.object(actions.powerShellWrapper, 'exec_powershell', return_value=[]) as execute, patch.object(actions.cmdShellWrapper, 'exec_cmd') as shell:
            self.assertTrue(actions.run_repair_windows_script())
            payload = self.repair_payload(execute)
            scan = payload.index('Dism.exe" /Online /Cleanup-Image /ScanHealth')
            restore = payload.index('Dism.exe" /Online /Cleanup-Image /RestoreHealth')
            sfc = payload.index('sfc.exe" /scannow')
            appx = payload.index('Get-AppxPackage -AllUsers')
            self.assertLess(scan, restore)
            self.assertLess(restore, sfc)
            self.assertLess(sfc, appx)
            self.assertIn("Add-AppxPackage -DisableDevelopmentMode -Register (Join-Path $_.InstallLocation 'AppXManifest.xml')", payload)
            self.assertNotIn('.bat', payload)
            shell.assert_not_called()

    def test_ntfs_repair_uses_normalized_configured_drive(self):
        with patch.object(actions, 'get_os', return_value=OS.WIN), patch.object(actions, 'effective_settings') as ini, patch.object(actions.powerShellWrapper, 'exec_powershell', return_value=[]) as execute:
            ini.return_value.get.return_value = ' e: '
            self.assertTrue(actions.run_repair_ntfs_on_d())
            payload = self.repair_payload(execute)
            self.assertIn("Write-Host 'Repairing E:'", payload)
            self.assertIn('chkdsk.exe" E: /f /r', payload)
            self.assertNotIn('.bat', payload)

    def test_invalid_drive_never_launches_repair(self):
        with patch.object(actions, 'get_os', return_value=OS.WIN), patch.object(actions, 'effective_settings') as ini, patch.object(actions.powerShellWrapper, 'exec_powershell') as execute:
            for value in ('D: & echo unsafe', 'D:; echo unsafe', '$env:SystemDrive', 'D:\\', ''):
                ini.return_value.get.return_value = value
                with self.subTest(value=value), self.assertRaises(ValueError):
                    actions.run_repair_ntfs_on_d()
            execute.assert_not_called()

    def test_failed_or_cancelled_console_start_returns_false(self):
        with patch.object(actions, 'get_os', return_value=OS.WIN), patch.object(actions.powerShellWrapper, 'exec_powershell', return_value=None):
            self.assertFalse(actions.run_repair_windows_script())

    def test_non_windows_actions_never_launch_console(self):
        with patch.object(actions, 'get_os', return_value=OS.MAC), patch.object(actions.powerShellWrapper, 'exec_powershell') as execute:
            self.assertFalse(actions.run_repair_windows_script())
            self.assertFalse(actions.run_repair_ntfs_on_d())
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
