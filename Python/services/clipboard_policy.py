"""Shared setting and decision for application-controlled clipboard commands."""

LABEL = 'Restrict clipboard in protected sessions'
DESCRIPTION = (
    'Block supported Cut, Copy and Paste commands across Logistics while session-only '
    'credentials or retained protected content are present. Clipboard history, sync '
    'and other apps remain under system control. Existing clipboard contents are kept.'
)
CLIPBOARD_COMMANDS = frozenset(('cut', 'copy', 'paste'))


def blocked(enabled, protection):
    return enabled and protection.protected()
