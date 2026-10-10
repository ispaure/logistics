from pathlib import Path
"""
UI contributions exposed by the Logistics Smart Home feature.
"""

from features.contributions import Feature, PageContribution, SettingsContribution

def _create_page(parent=None):
    from features.smart_home.ui.page import SmartHomePage

    return SmartHomePage(parent=parent)


def get_contributions() -> Feature:
    """Return UI contributions provided by Smart Home."""

    return Feature(
        id='smart_home', label='Smart Home',
        settings=[SettingsContribution('Configuration', 'smart_home_config',
                    config_files=(Path(__file__).with_name('config.ini'),))],
        pages=[
            PageContribution(
                name='Smart Home',
                page_id='smart_home',
                create_page=_create_page,
                order=30,
                navigation_icon='smart_home'
            )
        ]
    )
