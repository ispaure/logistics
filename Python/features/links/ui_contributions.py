"""
UI contributions exposed by the Logistics Links feature.
"""

from features.contributions import FeatureContributions, PageContribution

def _create_page(parent=None):
    from features.links.ui.page import LinksPage

    return LinksPage(parent=parent)


def get_contributions() -> FeatureContributions:
    """Return UI contributions provided by Links."""

    return FeatureContributions(
        pages=[
            PageContribution(
                name='Links',
                page_id='links',
                create_page=_create_page,
                order=40
            )
        ]
    )
