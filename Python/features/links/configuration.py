"""
Configuration access for the Logistics Links feature.
"""

from pathlib import Path

from commonUtils.fileTypes.iniType import INIFile


URLS_SECTION = 'URLs'
RESOLVE_IP_SECTION = 'ResolveIP'


def get_config_file_path() -> Path:
    """Return the Links feature configuration file."""

    return Path(__file__).resolve().parent / 'config.ini'


def get_url(config_key: str) -> str:
    """Return one configured Links URL."""

    ini = INIFile(get_config_file_path()).read()
    return ini.get(URLS_SECTION, config_key + '_str', fallback=ini.get(URLS_SECTION, config_key))


def get_resolve_ip(name: str) -> str:
    """Return a hostname replacement; legacy unsuffixed keys remain supported."""
    ini = INIFile(get_config_file_path()).read()
    return ini.get(RESOLVE_IP_SECTION, name + '_str', fallback=ini.get(RESOLVE_IP_SECTION, name))
