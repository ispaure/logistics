"""
Operating-system maintenance actions for the Logistics System Tools feature.
"""

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

from pathlib import Path

import config
import json
import re
from commonUtils.configuration.layered import effective_settings
from commonUtils.persistence import atomic_write_json
from features.preferences import preferences_path

from commonUtils.runtime.diagnostics import Severity, log
from commonUtils.runtime.platform import OS, get_os
from commonUtils.integrations.wrappers import cmdShellWrapper


# ----------------------------------------------------------------------------------------------------------------------
# WINDOWS

def run_repair_windows_script() -> bool:
    """Launch the Windows system-files repair script."""

    tool_name = 'Repair Windows System Files'

    if get_os() != OS.WIN:
        log(Severity.WARNING, tool_name, 'This command is only supported on Windows.')
        return False

    script_path = Path(config.LogisticsConfig().path_logistics_scripts, 'windows_system_files_repair.bat')
    command = f'start "" "{script_path}"'

    if not script_path.is_file():
        raise FileNotFoundError(script_path)
    return cmdShellWrapper.exec_cmd(command, wait_for_output=False) is not False


def run_repair_ntfs_on_d() -> bool:
    """Launch the Windows NTFS repair script for D:."""

    tool_name = 'Repair NTFS'

    if get_os() != OS.WIN:
        log(Severity.WARNING, tool_name, 'This command is only supported on Windows.')
        return False

    script_path = Path(config.LogisticsConfig().path_logistics_scripts, 'repair_ntfs_on_D.bat')
    drive = effective_settings(Path(__file__).with_name('config.ini')).get('Windows', 'ntfs_drive', fallback='D:').strip().upper()
    if re.fullmatch(r'[A-Z]:', drive) is None:
        raise ValueError('NTFS drive must be a drive letter such as D:.')
    command = f'start "" "{script_path}" {drive}'

    if not script_path.is_file():
        raise FileNotFoundError(script_path)
    return cmdShellWrapper.exec_cmd(command, wait_for_output=False) is not False


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
