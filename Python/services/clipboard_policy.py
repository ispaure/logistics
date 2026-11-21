"""Shared setting and decision for application-controlled clipboard commands."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

LABEL = 'Restrict clipboard in protected sessions'
DESCRIPTION = (
    'Block supported Cut, Copy and Paste commands across Logistics while session-only '
    'credentials or retained protected content are present. Clipboard history, sync '
    'and other apps remain under system control. Existing clipboard contents are kept.'
)
CLIPBOARD_COMMANDS = frozenset(('cut', 'copy', 'paste'))


def blocked(enabled, protection):
    return enabled and protection.protected()
