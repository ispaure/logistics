"""
Debug UI contributions exposed by System Tools.
"""

from commonUtils.osUtils import OS, get_os

from features.contributions import DebugActionContribution, FeatureContributions
from features.system_tools import actions


def get_contributions() -> FeatureContributions:
    current_os = get_os()

    return FeatureContributions(
        debug_actions=[
            DebugActionContribution(
                name='Windows System Files Repair',
                callback=actions.run_repair_windows_script,
                description='Launch the Windows system-files repair script.',
                destructive=True,
                enabled=current_os == OS.WIN,
                order=10
            ),
            DebugActionContribution(
                name='Repair NTFS on D:/',
                callback=actions.run_repair_ntfs_on_d,
                description='Launch the configured Windows NTFS repair script for D:.',
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
