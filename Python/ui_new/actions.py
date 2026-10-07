"""Execute contributed UI actions consistently across application pages."""

from collections.abc import Callable

from commonUtils import ui
from features.contributions import DebugActionContribution, UIAction
from ui_new import workflows


def execute_action(
    action: UIAction | DebugActionContribution,
    parent=None,
    *,
    subject: str | None = None,
    refresh: Callable[[], None] | None = None,
) -> bool:
    """Run an enabled action; workflow dialogs own their confirmation and refresh."""

    if not action.enabled:
        return False
    if action.workflow_id is not None:
        workflows.open_workflow(action.workflow_id, data=action.workflow_data, parent=parent)
        return True

    if action.destructive:
        debug_action = isinstance(action, DebugActionContribution)
        title = 'Confirm Debug Action' if debug_action else 'Confirm Action'
        scope = 'files or system configuration' if debug_action else 'files'
        target = f' for "{subject}"' if subject is not None else ''
        message = f'Run "{action.name}"{target}?\n\nThis action may modify {scope}.'
        if not ui.display_msg_box_ok_cancel(title, message):
            return False

    action.callback()
    if action.destructive and refresh is not None:
        refresh()
    return True
