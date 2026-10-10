"""
Detection helpers for the Logistics Flight Simulator feature.
"""

from pathlib import Path

from commonUtils.filesystem import files as fileUtils


def get_xp12_dir() -> Path:
    """Return the expected X-Plane 12 Steam installation directory."""

    return Path(fileUtils.get_user_application_support(), 'Steam', 'steamapps', 'common', 'X-Plane 12')


def get_xp12_preferences_path() -> Path:
    """Return the X-Plane 12 preferences file path."""

    return get_xp12_dir() / 'Output' / 'Preferences' / 'X-Plane.prf'


def get_xp12_window_positions_path() -> Path:
    """Return the X-Plane 12 window positions preferences file path."""

    return get_xp12_dir() / 'Output' / 'Preferences' / 'X-Plane Window Positions.prf'
