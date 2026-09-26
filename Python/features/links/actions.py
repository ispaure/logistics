"""
Actions for the Logistics Links feature.
"""

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

import webbrowser

import config

from commonUtils import configUtils


# ----------------------------------------------------------------------------------------------------------------------
# ACTIONS

def open_config_file_url(entry_str: str) -> None:
    """Open a URL stored in configFile.ini."""

    print('Attempting to open URL')

    config_file_path = config.get_config_file_path()
    url = configUtils.config_section_map(config_file_path, 'URLs', entry_str)

    if '<' in url and '>' in url:
        computer_ips = {
            'goat-pc': configUtils.config_section_map(config_file_path, 'ResolveIP', 'goat-pc'),
            'yagi-mac': configUtils.config_section_map(config_file_path, 'ResolveIP', 'yagi-mac'),
        }

        for key, value in computer_ips.items():
            url = url.replace(f'<{key}>', value)

    webbrowser.open(url)
