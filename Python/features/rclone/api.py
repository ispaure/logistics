"""
Public API for the Logistics rclone feature.

This module provides the interface Logistics should use when interacting
with rclone.
"""

from . import credentials, mounts


def initialize() -> None:
    """Initialize the rclone feature."""

    credentials.add_logistics_remote_to_rclone_conf()
    mounts.initialize()
