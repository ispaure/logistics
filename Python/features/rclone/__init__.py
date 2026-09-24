"""
rclone feature integration for Logistics.
"""

from . import api


FEATURE_NAME = "rclone"


def initialize() -> None:
    """
    Initialize the rclone feature.
    """

    api.initialize()
