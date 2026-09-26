"""
UI contributions exposed by the Logistics Links feature.
"""

from features.contributions import FeatureContributions, PageContribution


def get_contributions() -> FeatureContributions:
    """Return UI contributions provided by Links."""

    return FeatureContributions(
        pages=[
            PageContribution(
                name='Links',
                page_id='links',
                order=40
            )
        ]
    )
