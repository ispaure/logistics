"""
rclone synchronization for the Logistics rclone feature.
"""

from pathlib import Path

from commonUtils.osUtils import OS, get_os
from commonUtils.wrappers import cmdShellWrapper

from . import executable


def rclone_sync(source_path: str | Path, destination_path: str | Path, query=False, wait_for_output=False, dry_run=False, track_renames=False, bw_limit=None):
    source_path_str = str(source_path)
    destination_path_str = str(destination_path)

    baseline = f'"{executable.get_rclone_path()}" sync --progress --copy-links '

    if track_renames:
        baseline += '--track-renames '

    if '-VM' in source_path_str:
        baseline += '--transfers=1 '
    else:
        baseline += '--transfers=10 '

    if bw_limit is not None:
        baseline += f'--bwlimit {bw_limit}M '

    if dry_run:
        baseline += '--dry-run '

    baseline += f'"{source_path_str}" "{destination_path_str}"'

    if not Path(destination_path).exists():
        match get_os():
            case OS.WIN:
                if len(destination_path_str) > 1 and destination_path_str[1] == ':':
                    Path(destination_path).mkdir(parents=True, exist_ok=True)

            case OS.MAC | OS.LINUX:
                if destination_path_str.startswith('/'):
                    Path(destination_path).mkdir(parents=True, exist_ok=True)

    if query:
        output_lines = cmdShellWrapper.exec_cmd(baseline, wait_for_output=True)
        return rclone_sync_process_query(source_path_str, destination_path_str, output_lines)

    cmdShellWrapper.exec_cmd(baseline, wait_for_output=wait_for_output, in_new_window=True)
    return None


def rclone_sync_process_query(source_path: str | Path, destination_path: str | Path, output_lines):
    """
    Process output from an rclone sync dry run and return the files that would be copied.
    """

    source_path_str = str(source_path)
    destination_path_str = str(destination_path)

    copy_lst = []

    for output_line in output_lines:
        if 'Skipped copy as --dry-run is set' not in output_line:
            continue

        notice_loc = output_line.find('NOTICE: ')
        file_path_begin_loc = notice_loc + len('NOTICE: ')
        file_path_end_loc = output_line[file_path_begin_loc:].find(':')
        file_path_to_copy = output_line[file_path_begin_loc:file_path_begin_loc + file_path_end_loc]

        match get_os():
            case OS.WIN:
                if len(source_path_str) > 1 and source_path_str[1] == ':':
                    file_path_source = str(Path(source_path_str, file_path_to_copy))
                else:
                    file_path_source = source_path_str + file_path_to_copy.replace('\\', '/')

                if len(destination_path_str) > 1 and destination_path_str[1] == ':':
                    file_path_destination = str(Path(destination_path_str, file_path_to_copy))
                else:
                    file_path_destination = destination_path_str + file_path_to_copy.replace('\\', '/')

            case OS.MAC | OS.LINUX:
                if source_path_str.startswith('/'):
                    file_path_source = str(Path(source_path_str, file_path_to_copy))
                else:
                    file_path_source = source_path_str + file_path_to_copy

                if destination_path_str.startswith('/'):
                    file_path_destination = str(Path(destination_path_str, file_path_to_copy))
                else:
                    file_path_destination = destination_path_str + file_path_to_copy

        copy_lst.append([file_path_source, file_path_destination])

    return {'COPY': copy_lst}
