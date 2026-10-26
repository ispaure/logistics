"""Explicit upload confirmation shared by the CLI and small desktop launcher."""
MARKER = 'LOGISTICS_UPLOAD_CONFIRM:'


def gui_input(prompt):
    from build_manager.deployment_commands import confirmation_input
    return confirmation_input(prompt, marker=MARKER)
