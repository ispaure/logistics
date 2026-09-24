"""
Public API for the Logistics rclone feature.

This module provides the interface Logistics should use when interacting
with rclone. The existing implementation currently remains in
wrappers.rcloneWrapper and will be migrated gradually.
"""

from wrappers import rcloneWrapper


def initialize() -> None:
    """
    Initialize the rclone feature.
    """

    rcloneWrapper.add_logistics_remote_to_rclone_conf()
    rcloneWrapper.clear_mounts()
    rcloneWrapper.mount_all_rclone_conf_remotes(timeout=2)
    rcloneWrapper.get_all_remote_class()