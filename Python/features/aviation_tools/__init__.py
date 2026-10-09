"""Flight Tools integrated into Logistics as an optional feature."""
from features.contributions import Feature, PageContribution


def create_page(parent=None):
    from .ui.page import AviationToolsPage
    return AviationToolsPage(parent)


def register():
    return Feature(
        id='aviation_tools', label='Aviation Tools',
        pages=[PageContribution('Aviation Tools', 'aviation_tools', create_page, order=40)],
    )
