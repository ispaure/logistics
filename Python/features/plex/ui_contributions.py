"""
Debug UI contributions exposed by Plex.
"""

from features.contributions import DebugActionContribution, FeatureContributions
from features.plex import database


def get_contributions() -> FeatureContributions:
    return FeatureContributions(
        debug_actions=[
            DebugActionContribution(
                name='PLEXDB - Parse Database Test',
                callback=database.test_script,
                description='Run the existing Plex database comparison/test script.'
            )
        ]
    )
