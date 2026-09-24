"""
rclone feature integration for Logistics.
"""

from wrappers import rcloneWrapper


FEATURE_NAME = "rclone"


def initialize() -> None:
    """
    Initialize the rclone feature.

    This preserves the existing Logistics startup behaviour for rclone.
    """

    rcloneWrapper.add_logistics_remote_to_rclone_conf()
    rcloneWrapper.clear_mounts()
    rcloneWrapper.mount_all_rclone_conf_remotes(timeout=2)
    rcloneWrapper.get_all_remote_class()