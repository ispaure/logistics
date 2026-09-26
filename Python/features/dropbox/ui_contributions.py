"""
Debug UI contributions exposed by Dropbox.
"""

from features.contributions import DebugActionContribution, FeatureContributions, WorkflowContribution

def _open_conflicts(data=None, parent=None):
    from features.dropbox.ui.dialogs import DropboxConflictsDialog

    dialog = DropboxConflictsDialog(initial_path=data, parent=parent)
    return dialog.exec()


def get_contributions() -> FeatureContributions:
    return FeatureContributions(
        debug_actions=[
            DebugActionContribution(
                name='Conflicting Copies...',
                workflow_id='debug_dropbox_conflicts',
                destructive=True
            )
        ],
        workflows=[
            WorkflowContribution(
                workflow_id='debug_dropbox_conflicts',
                handler=_open_conflicts
            )
        ]
    )
