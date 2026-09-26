"""
Debug UI contributions exposed by File Tools.
"""

from features.contributions import DebugActionContribution, FeatureContributions


def get_contributions() -> FeatureContributions:
    return FeatureContributions(
        debug_actions=[
            DebugActionContribution(
                name='List Weird Characters...',
                workflow_id='debug_file_tools_weird_chars',
                description='List files containing configured problematic Unicode characters.',
                order=10
            ),
            DebugActionContribution(
                name='Bulk Delete PYC...',
                workflow_id='debug_file_tools_delete_pyc',
                destructive=True,
                order=20
            ),
        ]
    )
