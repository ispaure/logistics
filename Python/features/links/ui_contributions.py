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
        id='links', label='Links',
        settings=[SettingsContribution('Configuration', 'links_config', _create_settings,
                    config_files=(Path(__file__).with_name('config.ini'),))],
        pages=[
            PageContribution(
                name='Links',
                page_id='links',
                create_page=_create_page,
                order=40
            )
        ]
    )


def _create_settings(parent=None):
    from commonUtils.ui import pyside as qt
    return qt.QLabel('Edit the links configuration below. Changes may require restarting Logistics.', parent)
