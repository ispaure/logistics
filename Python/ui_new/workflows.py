"""
UI workflow dispatcher for the replacement Logistics frontend.

Features identify workflows by ID without importing concrete UI modules.
"""


def open_workflow(workflow_id: str, data=None, parent=None):
    """Open a named frontend workflow."""

    match workflow_id:
        case 'rclone_push':
            from ui_new.dialogs.rclone_push import RclonePushDialog

            dialog = RclonePushDialog(data, parent=parent)
            return dialog.exec()

        case 'calibre_manage':
            from ui_new.dialogs.calibre_manage import CalibreManageDialog

            dialog = CalibreManageDialog(data, parent=parent)
            return dialog.exec()

        case 'plex_manage':
            from ui_new.dialogs.plex_manage import PlexManagePMSDialog

            dialog = PlexManagePMSDialog(data, parent=parent)
            return dialog.exec()

        case _ if workflow_id.startswith('debug_'):
            from ui_new.dialogs.debug_tools import open_debug_tool

            return open_debug_tool(workflow_id, data=data, parent=parent)

        case _:
            raise ValueError(f'Unknown UI workflow: {workflow_id}')
