"""
Configuration access for the Logistics Links feature.
"""

from pathlib import Path

from commonUtils import configUtils


URLS_SECTION = 'URLs'
RESOLVE_IP_SECTION = 'ResolveIP'


def get_config_file_path() -> Path:
    """Return the Links feature configuration file."""

    return Path(__file__).resolve().parent / 'config.ini'


def get_url(config_key: str) -> str:
    """Return one configured Links URL."""

    return configUtils.config_section_map(
        get_config_file_path(),
        URLS_SECTION,
        config_key
    )


def get_resolve_ip(name: str) -> str:
    """Return one configured hostname/IP replacement used by Links."""

    return configUtils.config_section_map(
        get_config_file_path(),
        RESOLVE_IP_SECTION,
        name
    )
