"""
Detection helpers for the Logistics Flight Simulator feature.
"""

from pathlib import Path

from commonUtils.filesystem import files as fileUtils


def get_xp12_dir() -> Path:
    """Return the expected X-Plane 12 Steam installation directory."""

    from commonUtils.configuration.layered import effective_settings
    ini = effective_settings(Path(__file__).with_name('config.ini'))
    configured = ini.get('XPlane', 'installation_path', fallback='')
    if configured:
        return Path(configured).expanduser()
    return Path(fileUtils.get_user_application_support(), 'Steam', 'steamapps', 'common', 'X-Plane 12')


def get_xp12_preferences_path() -> Path:
    """Return the X-Plane 12 preferences file path."""

    return get_xp12_dir() / 'Output' / 'Preferences' / 'X-Plane.prf'


def get_xp12_window_positions_path() -> Path:
    """Return the X-Plane 12 window positions preferences file path."""

    return get_xp12_dir() / 'Output' / 'Preferences' / 'X-Plane Window Positions.prf'
