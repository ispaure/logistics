"""Flight Tools integrated into Logistics as an optional feature."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

FEATURE_DESCRIPTION = 'Calculate flight distances, headings and aircraft performance.'
from features.contributions import Feature, PageContribution


def create_page(parent=None):
    from .ui.page import AviationToolsPage
    return AviationToolsPage(parent)


def register():
    return Feature(
        id='aviation_tools', label='Aviation Tools',
        pages=[PageContribution('Aviation Tools', 'aviation_tools', create_page, order=40, navigation_icon='aviation')],
    )
