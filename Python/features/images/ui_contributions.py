"""
Debug UI contributions exposed by Images.
"""

from features.contributions import DebugActionContribution, FeatureContributions


def get_contributions() -> FeatureContributions:
    return FeatureContributions(
        debug_actions=[
            DebugActionContribution(
                name='Batch Compress Images...',
                workflow_id='debug_images_compress',
                destructive=True,
                order=10
            ),
            DebugActionContribution(
                name='JPG EXIF - Set Comments...',
                workflow_id='debug_images_exif_comments',
                destructive=True,
                order=20
            ),
        ]
    )
