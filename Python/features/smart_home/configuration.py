"""
Configuration access for the Logistics Smart Home feature.
"""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from pathlib import Path

from commonUtils.configuration.layered import effective_settings


PHILIPS_HUE_SECTION = 'PhilipsHue'
BRIDGE_ADDRESS_KEY = 'bridge_address'


def get_config_file_path() -> Path:
    """Return the Smart Home feature configuration file."""

    return Path(__file__).resolve().parent / 'config.ini'


def get_philips_hue_bridge_address() -> str:
    """Return the configured Philips Hue bridge address."""

    ini = effective_settings(get_config_file_path())
    return ini.get(PHILIPS_HUE_SECTION, BRIDGE_ADDRESS_KEY + '_str',
                   fallback=ini.get(PHILIPS_HUE_SECTION, BRIDGE_ADDRESS_KEY, fallback=None))
