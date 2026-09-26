"""
UI contributions exposed by the Logistics Smart Home feature.
"""

from features.contributions import FeatureContributions, PageContribution


def get_contributions() -> FeatureContributions:
    """Return UI contributions provided by Smart Home."""

    return FeatureContributions(
        pages=[
            PageContribution(
                name='Smart Home',
                page_id='smart_home',
                order=30
            )
        ]
    )
