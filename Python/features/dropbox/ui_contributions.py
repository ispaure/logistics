"""
Debug UI contributions exposed by Dropbox.
"""

from features.contributions import DebugActionContribution, FeatureContributions


def get_contributions() -> FeatureContributions:
    return FeatureContributions(
        debug_actions=[
            DebugActionContribution(
                name='Conflicting Copies...',
                workflow_id='debug_dropbox_conflicts',
                destructive=True
            )
        ]
    )
