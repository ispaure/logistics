"""Explicit upload confirmation shared by the CLI and small desktop launcher."""
import json

MARKER = 'LOGISTICS_UPLOAD_CONFIRM:'


def gui_input(prompt):
    print('\n' + MARKER + json.dumps(prompt), flush=True)
    return input()
