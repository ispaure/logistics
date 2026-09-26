"""
Actions for the Logistics Links feature.
"""

import webbrowser

from features.links import configuration


def open_config_file_url(entry_str: str) -> None:
    """Open a URL stored in the Links feature config.ini."""

    print('Attempting to open URL')

    url = configuration.get_url(entry_str)

    if '<' in url and '>' in url:
        computer_ips = {
            'goat-pc': configuration.get_resolve_ip('goat-pc'),
            'yagi-mac': configuration.get_resolve_ip('yagi-mac'),
        }

        for key, value in computer_ips.items():
            url = url.replace(f'<{key}>', value)

    webbrowser.open(url)
