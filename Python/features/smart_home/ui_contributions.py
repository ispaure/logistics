from pathlib import Path
"""
UI contributions exposed by the Logistics Smart Home feature.
"""

from features.contributions import FeatureContributions, PageContribution, SettingsContribution

def _create_page(parent=None):
    from features.smart_home.ui.page import SmartHomePage

    return SmartHomePage(parent=parent)


def get_contributions() -> FeatureContributions:
    """Return UI contributions provided by Smart Home."""

    return FeatureContributions(
        settings=[SettingsContribution('Configuration', 'smart_home_config', _create_settings,
                    config_files=(Path(__file__).with_name('config.ini'),))],
        pages=[
            PageContribution(
                name='Smart Home',
                page_id='smart_home',
                create_page=_create_page,
                order=30
            )
        ]
    )


def _create_settings(parent=None):
    from commonUtils.ui import pyside as qt
    return qt.QLabel('Edit the smart home configuration below. Changes may require restarting Logistics.', parent)
