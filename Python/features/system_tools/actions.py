"""
Operating-system maintenance actions for the Logistics System Tools feature.
"""

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

from pathlib import Path

import base64
import json
import re
from commonUtils.configuration.layered import effective_settings
from commonUtils.persistence import atomic_write_json
from features.preferences import preferences_path

from commonUtils.runtime.diagnostics import Severity, log
from commonUtils.runtime.platform import OS, get_os
from commonUtils.integrations.wrappers import cmdShellWrapper, powerShellWrapper


# ----------------------------------------------------------------------------------------------------------------------
# WINDOWS

def _launch_windows_repair(command: str) -> bool:
    """Use the shared PowerShell wrapper to request a separate elevated console."""
    encoded = base64.b64encode(command.encode('utf-16-le')).decode('ascii')
    launcher = ("Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -Verb RunAs "
                "-ArgumentList '-NoProfile', '-NoExit', '-EncodedCommand', "
                f"'{encoded}' -ErrorAction Stop")
    # Wait only for console startup/UAC, not for the repair commands to finish.
    # The wrapper's synchronous path passes arguments directly, without CMD.
    return powerShellWrapper.exec_powershell(launcher) is not None


def run_repair_windows_script() -> bool:
    """Run the system-files repair commands in an administrator console."""

    tool_name = 'Repair Windows System Files'

    if get_os() != OS.WIN:
        log(Severity.WARNING, tool_name, 'This command is only supported on Windows.')
        return False

    return _launch_windows_repair(
        "$Host.UI.RawUI.WindowTitle = 'Logistics - Windows System Files Repair'; "
        r'& "$env:SystemRoot\System32\Dism.exe" /Online /Cleanup-Image /ScanHealth; '
        r'& "$env:SystemRoot\System32\Dism.exe" /Online /Cleanup-Image /RestoreHealth; '
        r'& "$env:SystemRoot\System32\sfc.exe" /scannow; '
        'Get-AppxPackage -AllUsers | ForEach-Object { '
        "Add-AppxPackage -DisableDevelopmentMode -Register (Join-Path $_.InstallLocation 'AppXManifest.xml') }"
    )


def run_repair_ntfs_on_d() -> bool:
    """Run CHKDSK for the configured drive in an administrator console."""

    tool_name = 'Repair NTFS'

    if get_os() != OS.WIN:
        log(Severity.WARNING, tool_name, 'This command is only supported on Windows.')
        return False

    drive = effective_settings(Path(__file__).with_name('config.ini')).get('Windows', 'ntfs_drive', fallback='D:').strip().upper()
    if re.fullmatch(r'[A-Z]:', drive) is None:
        raise ValueError('NTFS drive must be a drive letter such as D:.')
    return _launch_windows_repair(
        f"$Host.UI.RawUI.WindowTitle = 'Logistics - Repair {drive}'; "
        f"Write-Host 'Repairing {drive}'; "
        rf'& "$env:SystemRoot\System32\chkdsk.exe" {drive} /f /r'
    )


# ----------------------------------------------------------------------------------------------------------------------
# MACOS

def disable_macos_lid_sleep() -> bool:
    """Disable battery-powered lid sleep on macOS."""

    tool_name = 'Disable macOS Lid Sleep'

    if get_os() != OS.MAC:
        log(Severity.WARNING, tool_name, 'This command is only supported on macOS.')
        return False

    backup = preferences_path().with_name('battery-power.json')
    if not backup.exists():
        result = cmdShellWrapper.run_command(['pmset', '-g', 'custom'], timeout=5)
        if not result.success:
            return False
        battery = False
        values = {}
        for line in result.stdout:
            if line.strip().endswith('Power:'):
                battery = line.strip() == 'Battery Power:'
            parts = line.split()
            if battery and len(parts) == 2 and parts[0] == 'sleep' and parts[1].isdigit():
                values[parts[0]] = int(parts[1])
        global_settings = cmdShellWrapper.run_command(['pmset', '-g'], timeout=5)
        if not global_settings.success:
            return False
        for line in global_settings.stdout:
            parts = line.split()
            if len(parts) == 2 and parts[0] == 'SleepDisabled' and parts[1].isdigit():
                values['disablesleep'] = int(parts[1])
        if set(values) != {'sleep', 'disablesleep'}:
            raise ValueError('Could not read battery sleep and system sleep-disable settings. This action requires a Mac with battery power settings.')
        backup.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(backup, values)
    command = 'sudo pmset -b sleep 0 && sudo pmset -b disablesleep 1' 
    return cmdShellWrapper.exec_cmd(command, in_new_window=True) is not False


def enable_macos_lid_sleep() -> bool:
    """Restore battery-powered lid sleep settings on macOS."""

    tool_name = 'Enable macOS Lid Sleep'

    if get_os() != OS.MAC:
        log(Severity.WARNING, tool_name, 'This command is only supported on macOS.')
        return False

    backup = preferences_path().with_name('battery-power.json')
    if not backup.is_file():
        raise ValueError('No saved battery settings. Use macOS System Settings to choose sleep behavior.')
    values = json.loads(backup.read_text())
    if set(values) != {'sleep', 'disablesleep'} or any(type(value) is not int or value < 0 for value in values.values()):
        raise ValueError('Saved battery settings are invalid; the original file was kept.')
    command = f"sudo pmset -b sleep {values['sleep']} && sudo pmset -b disablesleep {values['disablesleep']}"
    return cmdShellWrapper.exec_cmd(command, in_new_window=True) is not False
