"""Explicit upload confirmation shared by the CLI and small desktop launcher."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

MARKER = 'LOGISTICS_UPLOAD_CONFIRM:'


def gui_input(prompt):
    from build_manager.deployment_commands import confirmation_input
    return confirmation_input(prompt, marker=MARKER)
