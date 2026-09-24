"""
rclone executable resolution for the Logistics rclone feature.
"""

from pathlib import Path

import config

from commonUtils.osUtils import Arch, OS, get_arch, get_os


def get_rclone_path() -> Path:
    """Return the platform-specific rclone executable path used by Logistics."""

    logistics_cfg = config.LogisticsConfig()

    match get_os():
        case OS.WIN:
            return Path(logistics_cfg.path_logistics_software_win, "rclone-2026", "rclone.exe")

        case OS.MAC:
            return Path(logistics_cfg.path_logistics_software_mac, "rclone", "rclone")

        case OS.LINUX:
            match get_arch():
                case Arch.X86_64:
                    return Path(logistics_cfg.path_logistics_software_linux, "rclone-v1.73.0-linux-amd64", "rclone")

                case Arch.ARM_64:
                    return Path(logistics_cfg.path_logistics_software_linux, "rclone-v1.73.1-linux-arm64", "rclone")

    raise RuntimeError(f"Unsupported platform for rclone: OS={get_os()}, architecture={get_arch()}")
