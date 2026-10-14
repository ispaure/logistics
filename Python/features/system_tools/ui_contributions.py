"""
Debug UI contributions exposed by System Tools.
"""

from pathlib import Path

from commonUtils.runtime.platform import OS, get_os

from features.contributions import DebugActionContribution, Feature, SettingsContribution
from features.system_tools import actions


def get_contributions() -> Feature:
    current_os = get_os()

    return Feature(
        id='system_tools', label='System Tools',
        settings=[SettingsContribution('Configuration', 'system_tools_config', config_files=(Path(__file__).with_name('config.ini'),))],
        debug_actions=[
            DebugActionContribution(
                name='Windows System Files Repair',
                callback=actions.run_repair_windows_script,
                description='Run DISM, SFC and AppX re-registration in an administrator console.',
                destructive=True,
                enabled=current_os == OS.WIN,
                order=10
            ),
            DebugActionContribution(
                name='Repair configured NTFS drive',
                callback=actions.run_repair_ntfs_on_d,
                description='Run CHKDSK /f /r in an administrator console for the drive selected in feature settings.',
                destructive=True,
                enabled=current_os == OS.WIN,
                order=20
            ),
            DebugActionContribution(
                name='Disable macOS Lid Sleep',
                callback=actions.disable_macos_lid_sleep,
                description='Disable battery-powered lid sleep on macOS.',
                destructive=True,
                enabled=current_os == OS.MAC,
                order=30
            ),
            DebugActionContribution(
                name='Enable macOS Lid Sleep',
                callback=actions.enable_macos_lid_sleep,
                description='Restore battery-powered lid sleep settings on macOS.',
                destructive=True,
                enabled=current_os == OS.MAC,
                order=40
            ),
        ]
    )
