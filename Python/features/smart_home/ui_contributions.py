"""
UI contributions exposed by the Logistics Smart Home feature.
"""

from features.contributions import FeatureContributions, PageContribution

def _create_page(parent=None):
    from features.smart_home.ui.page import SmartHomePage

    return SmartHomePage(parent=parent)


def get_contributions() -> FeatureContributions:
    """Return UI contributions provided by Smart Home."""

    return FeatureContributions(
        pages=[
            PageContribution(
                name='Smart Home',
                page_id='smart_home',
                create_page=_create_page,
                order=30
            )
        ]
    )
