"""
Actions for the Logistics Perforce feature.
"""

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

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