"""
Debug UI contributions exposed by Media.
"""

from features.contributions import DebugActionContribution, FeatureContributions


def get_contributions() -> FeatureContributions:
    return FeatureContributions(
        debug_actions=[
            DebugActionContribution(
                name='Rename MKA from CSV...',
                workflow_id='debug_media_rename_mka',
                destructive=True
            )
        ]
    )
