"""
Actions for the Logistics Perforce feature.
"""

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

import shlex

from commonUtils.osUtils import OS, get_os
from commonUtils.wrappers import cmdShellWrapper

from features.perforce import detection
from models.local_folder import LocalFolder


# ----------------------------------------------------------------------------------------------------------------------
# ACTIONS

def launch_server(folder: LocalFolder) -> bool:
    """Launch the configured Perforce server for a LocalFolder."""

    if get_os() != OS.LINUX:
        return False

    p4d_path = detection.get_p4d_path(folder)
    data_path = detection.get_data_path(folder)
    port = detection.get_port(folder)

    if p4d_path is None or data_path is None or port is None:
        return False

    command = f'./{p4d_path} -C1 -r ./{data_path} -p {port}'
    cmdShellWrapper.exec_cmd(command, in_new_window=True, cwd=folder.path)

    return True


def open_console(folder: LocalFolder) -> bool:
    """Open an interactive P4 console connected to this local server."""

    if get_os() != OS.LINUX:
        return False

    port = detection.get_port(folder)
    client_path = detection.get_p4_client_path(folder)
    if not port or not client_path:
        return False

    # Bare port numbers refer to the server running on this machine.
    address = f'localhost:{port}' if port.isdecimal() else port
    message = f'P4 console: {address}. Example: p4 -u marca passwd'
    command = (
        f'export P4PORT={shlex.quote(address)}; '
        f'p4() {{ command {shlex.quote(client_path)} -p {shlex.quote(address)} "$@"; }}; '
        'export -f p4; '
        f'printf "%s\\n" {shlex.quote(message)}; '
        'exec bash --norc -i'
    )
    # Explicit interactive shell also works with terminals that only hold
    # their window open after the supplied command completes.
    result = cmdShellWrapper.exec_cmd(command, in_new_window=True, cwd=folder.path)
    return result is not False
