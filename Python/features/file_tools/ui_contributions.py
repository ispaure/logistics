"""
Debug UI contributions exposed by File Tools.
"""

from features.contributions import DebugActionContribution, FeatureContributions, WorkflowContribution

def _open_weird_characters(data=None, parent=None):
    from features.file_tools.ui.dialogs import WeirdCharactersDialog

    dialog = WeirdCharactersDialog(initial_path=data, parent=parent)
    return dialog.exec()


def _open_delete_pyc(data=None, parent=None):
    from features.file_tools.ui.dialogs import DeletePycDialog

    dialog = DeletePycDialog(initial_path=data, parent=parent)
    return dialog.exec()


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
        ],
        workflows=[
            WorkflowContribution('debug_file_tools_weird_chars', _open_weird_characters),
            WorkflowContribution('debug_file_tools_delete_pyc', _open_delete_pyc),
        ]
    )
