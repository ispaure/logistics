"""
Operating-system maintenance actions for the Logistics System Tools feature.
"""

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

from pathlib import Path

import config

from commonUtils.debugUtils import Severity, log
from commonUtils.osUtils import OS, get_os
from commonUtils.wrappers import cmdShellWrapper


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

    cmdShellWrapper.exec_cmd(command, wait_for_output=False)
    return True


def run_repair_ntfs_on_d() -> bool:
    """Launch the Windows NTFS repair script for D:."""

    tool_name = 'Repair NTFS on D'

    if get_os() != OS.WIN:
        log(Severity.WARNING, tool_name, 'This command is only supported on Windows.')
        return False

    script_path = Path(config.LogisticsConfig().path_logistics_scripts, 'repair_ntfs_on_D.bat')
    command = f'start "" "{script_path}"'

    cmdShellWrapper.exec_cmd(command, wait_for_output=False)
    return True


# ----------------------------------------------------------------------------------------------------------------------
# MACOS

def disable_macos_lid_sleep() -> bool:
    """Disable battery-powered lid sleep on macOS."""

    tool_name = 'Disable macOS Lid Sleep'

    if get_os() != OS.MAC:
        log(Severity.WARNING, tool_name, 'This command is only supported on macOS.')
        return False

    command = 'sudo pmset -b sleep 0; sudo pmset -b disablesleep 1'
    cmdShellWrapper.exec_cmd(command, wait_for_output=True)

    print('Disabled macOS Lid Sleep!')
    return True


def enable_macos_lid_sleep() -> bool:
    """Restore battery-powered lid sleep settings on macOS."""

    tool_name = 'Enable macOS Lid Sleep'

    if get_os() != OS.MAC:
        log(Severity.WARNING, tool_name, 'This command is only supported on macOS.')
        return False

    command = 'sudo pmset -b sleep 5; sudo pmset -b disablesleep 0'
    cmdShellWrapper.exec_cmd(command, wait_for_output=True)

    print('Enabled macOS Lid Sleep!')
    return True
