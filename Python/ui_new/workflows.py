"""
Workflow resolution for the replacement Logistics UI.
"""

from ui.calibre import uiManageCalibre


def open_workflow(workflow_id: str, data=None, parent=None):
    """
    Resolve and open a named UI workflow.

    Features expose workflow identifiers without depending on ui_new directly.
    The replacement UI maps those identifiers to concrete dialogs/windows here.
    """

    match workflow_id:
        case 'calibre_manage':
            manage_window = uiManageCalibre.ManageCalibre(data)
            manage_window.display_ui()
            return manage_window

        case 'rclone_push':
            from ui_new.dialogs.rclone_push import RclonePushDialog

            dialog = RclonePushDialog(data, parent=parent)
            return dialog.exec()

        case _ if workflow_id.startswith('debug_'):
            from ui_new.dialogs.debug_tools import open_debug_tool

            return open_debug_tool(workflow_id, data=data, parent=parent)

        case _:
            raise ValueError(f'Unknown UI workflow: {workflow_id}')
