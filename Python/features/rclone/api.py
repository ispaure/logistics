"""
Public API for the Logistics rclone feature.

This module provides the interface Logistics should use when interacting
with rclone itself.
"""

from . import credentials


def initialize() -> None:
    """Initialize rclone configuration/credentials."""

    credentials.add_logistics_remote_to_rclone_conf()
