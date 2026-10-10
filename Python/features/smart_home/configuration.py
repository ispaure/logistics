"""
Configuration access for the Logistics Smart Home feature.
"""

from pathlib import Path

from commonUtils.formats.iniType import INIFile


PHILIPS_HUE_SECTION = 'PhilipsHue'
BRIDGE_ADDRESS_KEY = 'bridge_address'


def get_config_file_path() -> Path:
    """Return the Smart Home feature configuration file."""

    return Path(__file__).resolve().parent / 'config.ini'


def get_philips_hue_bridge_address() -> str:
    """Return the configured Philips Hue bridge address."""

    ini = INIFile(get_config_file_path()).read()
    return ini.get(PHILIPS_HUE_SECTION, BRIDGE_ADDRESS_KEY + '_str',
                   fallback=ini.get(PHILIPS_HUE_SECTION, BRIDGE_ADDRESS_KEY))
