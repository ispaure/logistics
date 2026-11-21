# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from pathlib import Path
"""
UI contributions exposed by the Logistics Links feature.
"""

from features.contributions import Feature, PageContribution, SettingsContribution

def _create_page(parent=None):
    from features.links.ui.page import LinksPage

    return LinksPage(parent=parent)


def get_contributions() -> Feature:
    """Return UI contributions provided by Links."""

    return Feature(
        id='links', label='Personal Links',
        settings=[SettingsContribution('Configuration', 'links_config',
                    config_files=(Path(__file__).with_name('config.ini'),))],
        pages=[
            PageContribution(
                name='Links',
                page_id='links',
                create_page=_create_page,
                order=40,
                navigation_icon='links'
            )
        ]
    )
