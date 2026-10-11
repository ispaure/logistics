"""
Actions for the Logistics Links feature.
"""

import webbrowser
from urllib.parse import urlsplit
import re

from features.links import configuration


def open_config_file_url(entry_str: str) -> None:
    """Open a URL stored in the Links feature config.ini."""

    url = configuration.get_url(entry_str)

    if not url:
        raise ValueError(f'No URL configured for {entry_str}')
    if '<' in url and '>' in url:
        computer_ips = {
            'goat-pc': configuration.get_resolve_ip('goat-pc'),
            'yagi-mac': configuration.get_resolve_ip('yagi-mac'),
        }

        for key, value in computer_ips.items():
            url = url.replace(f'<{key}>', value or '')

    parsed = urlsplit(url)
    if re.search(r'[<>\s]', url) or parsed.scheme not in ('https', 'http') or not parsed.hostname:
        raise ValueError(f'Configure a valid HTTP or HTTPS URL for {entry_str}')
    return webbrowser.open(url)
