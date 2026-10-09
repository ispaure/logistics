"""
rclone synchronization for the Logistics rclone feature.
"""

from pathlib import Path

from commonUtils.osUtils import OS, get_os
from commonUtils.wrappers import cmdShellWrapper

from . import executable


def rclone_sync(
    source_path: str | Path,
    destination_path: str | Path,
    *,
    config_path: str | Path,
    query=False,
    wait_for_output=False,
    dry_run=False,
    track_renames=False,
    bw_limit=None,
    integrated=True
):
    """Synchronize using one explicit config.

    GUI transfers return True when accepted; the progress window owns their actual
    exit result. Query and explicitly synchronous callers retain their legacy API.
    """

    rclone_path = executable.ensure_rclone()
    if rclone_path is None:
        return False

    source_path_str = str(source_path)
    destination_path_str = str(destination_path)
    arguments = build_sync_arguments(rclone_path, source_path, destination_path,
        config_path=config_path, track_renames=track_renames, bw_limit=bw_limit,
        dry_run=dry_run, integrated=integrated and not query and not wait_for_output)
    import shlex
    import subprocess
    baseline = subprocess.list2cmdline(arguments) if get_os() == OS.WIN else shlex.join(arguments)

    if not Path(destination_path).exists():
        match get_os():
            case OS.WIN:
                if len(destination_path_str) > 1 and destination_path_str[1] == ':':
                    Path(destination_path).mkdir(parents=True, exist_ok=True)

            case OS.MAC | OS.LINUX:
                if destination_path_str.startswith('/'):
                    Path(destination_path).mkdir(parents=True, exist_ok=True)

    if query:
        output_lines = cmdShellWrapper.exec_cmd(
            baseline,
            wait_for_output=True
        )
        return rclone_sync_process_query(
            source_path_str,
            destination_path_str,
            output_lines
        )

    if integrated and not wait_for_output:
        from commonUtils.ui import pyside as qt
        application = qt.QApplication.instance()
        if application is not None and qt.QThread.currentThread() == application.thread():
            from commonUtils.ui.process_progress import open_process
            from .progress import RcloneProgressParser
            open_process(f'rclone sync — {source_path_str} → {destination_path_str}',
                         arguments[0], arguments[1:], parser=RcloneProgressParser())
            return True

    cmdShellWrapper.exec_cmd(
        baseline,
        wait_for_output=wait_for_output,
        in_new_window=True
    )
    return True


def build_sync_arguments(rclone_path, source_path, destination_path, *, config_path,
                         track_renames=False, bw_limit=None, dry_run=False, integrated=True):
    """Argument vector shared by UI and legacy callers; no shell interpretation."""
    arguments = [str(rclone_path), '--config', str(config_path), 'sync', '--copy-links']
    if integrated:
        # Leave rclone's retry policy untouched; observe its own retry messages.
        arguments += ['--use-json-log', '--stats', '1s', '--stats-log-level', 'NOTICE']
    else:
        arguments += ['--progress']
    if track_renames:
        arguments += ['--track-renames']
    arguments += ['--transfers=1' if '-VM' in str(source_path) else '--transfers=10']
    if bw_limit is not None:
        value = int(bw_limit)
        if value <= 0:
            raise ValueError('Bandwidth limit must be a positive number of MB/s')
        arguments += ['--bwlimit', f'{value}M']
    if dry_run:
        arguments += ['--dry-run']
    arguments += ['--', str(source_path), str(destination_path)]
    return arguments


def rclone_sync_process_query(
    source_path: str | Path,
    destination_path: str | Path,
    output_lines
):
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
        file_path_to_copy = output_line[
            file_path_begin_loc:file_path_begin_loc + file_path_end_loc
        ]

        match get_os():
            case OS.WIN:
                if len(source_path_str) > 1 and source_path_str[1] == ':':
                    file_path_source = str(
                        Path(source_path_str, file_path_to_copy)
                    )
                else:
                    file_path_source = (
                        source_path_str
                        + file_path_to_copy.replace('\\', '/')
                    )

                if (
                    len(destination_path_str) > 1
                    and destination_path_str[1] == ':'
                ):
                    file_path_destination = str(
                        Path(destination_path_str, file_path_to_copy)
                    )
                else:
                    file_path_destination = (
                        destination_path_str
                        + file_path_to_copy.replace('\\', '/')
                    )

            case OS.MAC | OS.LINUX:
                if source_path_str.startswith('/'):
                    file_path_source = str(
                        Path(source_path_str, file_path_to_copy)
                    )
                else:
                    file_path_source = source_path_str + file_path_to_copy

                if destination_path_str.startswith('/'):
                    file_path_destination = str(
                        Path(destination_path_str, file_path_to_copy)
                    )
                else:
                    file_path_destination = (
                        destination_path_str + file_path_to_copy
                    )

        copy_lst.append([file_path_source, file_path_destination])

    return {'COPY': copy_lst}
