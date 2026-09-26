"""
Debug UI contributions exposed by Media.
"""

from features.contributions import DebugActionContribution, FeatureContributions, WorkflowContribution

def _open_rename_mka(data=None, parent=None):
    from features.media.ui.dialogs import RenameMkaDialog

    dialog = RenameMkaDialog(initial_path=data, parent=parent)
    return dialog.exec()


def get_contributions() -> FeatureContributions:
    return FeatureContributions(
        debug_actions=[
            DebugActionContribution(
                name='Rename MKA from CSV...',
                workflow_id='debug_media_rename_mka',
                destructive=True
            )
        ],
        workflows=[
            WorkflowContribution(
                workflow_id='debug_media_rename_mka',
                handler=_open_rename_mka
            )
        ]
    )
