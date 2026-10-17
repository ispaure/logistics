"""
rclone synchronization for the Logistics rclone feature.
"""

from pathlib import Path

from commonUtils.runtime.platform import OS, get_os
from commonUtils.integrations.wrappers import cmdShellWrapper
from commonUtils.runtime.diagnostics import Severity, log

from features.rclone import executable, session
from features.rclone.transfers.transfer_options import TransferOptions


def rclone_sync(source_path, destination_path, *, config_path, query=False, wait_for_output=False,
                dry_run=False, track_renames=False, bw_limit=None, integrated=True, copy_links=True,
                cancelled=lambda: False, executable_path=None, excludes=None):
    """Preflight every local-to-remote push before starting a transfer."""
    options = dict(source_path=source_path, destination_path=destination_path, config_path=config_path,
                   query=query, wait_for_output=wait_for_output, dry_run=dry_run, track_renames=track_renames,
                   bw_limit=bw_limit, integrated=integrated, copy_links=copy_links, cancelled=cancelled,
                   executable_path=executable_path)
    # Existing local paths also support synthetic/local rclone remotes in tests.
    is_push = Path(source_path).is_dir() and ':' in str(destination_path) and not Path(destination_path).is_absolute()
    if is_push:
        from features.rclone.transfers.push_policy import load_excludes, validate_localcrypt_push
        from features.rclone.localcrypt.backend import for_path, storage_root
        options['excludes'] = load_excludes() if excludes is None else excludes
        item = for_path(source_path)
        boundary = storage_root().absolute()
        source = Path(source_path).absolute()
        if item is None and (source == boundary or boundary in source.parents):
            raise ValueError('LocalCrypt push has no valid credential mapping.')
        if item is None:
            from commonUtils.filesystem.local_access import check_local_path
            check_local_path(source, recursive=True)
        if item is not None:
            binary = executable_path or executable.ensure_rclone()
            if binary is None:
                return False
            options['executable_path'] = binary
            options['copy_links'] = False
            def validate(report, stopping):
                return validate_localcrypt_push(item, binary, cancelled=lambda: cancelled() or stopping(),
                                                report=report, cleanup=not (query or dry_run))
            from commonUtils.ui import pyside as qt
            app = qt.QApplication.instance()
            if not wait_for_output and app is not None and qt.QThread.currentThread() == app.thread():
                from commonUtils.ui.resource_picker import ResourceTaskDialog
                dialog = ResourceTaskDialog(None, 'Checking LocalCrypt before push')
                result = []
                def completed(value, error):
                    result.append((value, error))
                    dialog.accept()
                dialog.operation.completed.connect(completed)
                dialog.operation.start(validate, message='Checking encrypted storage…')
                dialog.exec()
                stopped = dialog.operation.cancelled.is_set()
                dialog.deleteLater()
                if stopped:
                    return False
                if not result or result[0][1]:
                    raise ValueError(result[0][1] if result else 'Push validation was cancelled.')
            else:
                validate(lambda *args: None, cancelled)
    if cancelled():
        return False
    return _run_sync(**options)


def _run_sync(
    source_path: str | Path,
    destination_path: str | Path,
    *,
    config_path: str | Path,
    query=False,
    wait_for_output=False,
    dry_run=False,
    track_renames=False,
    bw_limit=None,
    integrated=True,
    copy_links=True,
    cancelled=lambda: False,
    executable_path=None,
    excludes=()
):
    """Synchronize using one explicit config.

    GUI transfers return True when accepted; the progress window owns their actual
    exit result. Synchronous callers wait for the exit status; previews always use dry-run.
    """

    # Background callers preflight provisioning on the GUI thread and pass its path.
    rclone_path = executable_path if executable_path is not None else executable.ensure_rclone()
    if rclone_path is None:
        return False

    source_path_str = str(source_path)
    destination_path_str = str(destination_path)
    session_launch = session.launch(config_path, source_path, destination_path)
    environment = None
    if session_launch is not None:
        environment, source_path, destination_path = session_launch
        config_path = 'NUL' if get_os() == OS.WIN else '/dev/null'
    elif Path(config_path).suffix == '.session':
        raise ValueError('This credential session has ended. Unlock the package again.')
    arguments = build_sync_arguments(rclone_path, source_path, destination_path,
        config_path=config_path, track_renames=track_renames, bw_limit=bw_limit,
        dry_run=dry_run or query, integrated=integrated and not query and not wait_for_output, copy_links=copy_links, excludes=excludes)
    import shlex
    import subprocess
    baseline = subprocess.list2cmdline(arguments) if get_os() == OS.WIN else shlex.join(arguments)

    if not query and not dry_run and not Path(destination_path).exists():
        match get_os():
            case OS.WIN:
                if len(destination_path_str) > 1 and destination_path_str[1] == ':':
                    Path(destination_path).mkdir(parents=True, exist_ok=True)

            case OS.MAC | OS.LINUX:
                if destination_path_str.startswith('/'):
                    Path(destination_path).mkdir(parents=True, exist_ok=True)

    if query or wait_for_output:
        result = cmdShellWrapper.run_command(arguments, cancelled=cancelled, **({'environment': environment} if environment is not None else {}))
        if not result.success:
            detail = '\n'.join(result.stderr) or ('Cancelled' if result.cancelled else f'Exit status {result.returncode}')
            if query:
                raise RuntimeError(f'rclone preview failed: {detail}')
            log(Severity.ERROR, 'rclone sync', detail)
            return False
        if query:
            return rclone_sync_process_query(source_path_str, destination_path_str, result.lines)
        return True

    if integrated and not wait_for_output:
        from commonUtils.ui import pyside as qt
        application = qt.QApplication.instance()
        if application is not None and qt.QThread.currentThread() == application.thread():
            from commonUtils.ui.tasks.process_progress import open_process
            from features.rclone.transfers.progress import RcloneProgressParser
            open_process('rclone sync (dry run)' if dry_run else 'rclone sync',
                         arguments[0], arguments[1:], parser=RcloneProgressParser(),
                         context={'operation': 'Sync (dry run)' if dry_run else 'Sync', 'source': source_path_str,
                                  'destination': destination_path_str, 'dry_run': dry_run},
                         **({'environment': environment} if environment is not None else {}))
            return True

    if environment is not None:
        # Session secrets never enter terminal command strings or global env.
        result = cmdShellWrapper.run_command(arguments, environment=environment, cancelled=cancelled)
        if not result.success:
            log(Severity.ERROR, 'rclone sync', 'The session transfer failed or was cancelled.')
        return result.success
    return cmdShellWrapper.exec_cmd(baseline, wait_for_output=False, in_new_window=True) is not False


def build_sync_arguments(rclone_path, source_path, destination_path, *, config_path,
                         track_renames=False, bw_limit=None, dry_run=False, integrated=True, copy_links=True, excludes=()):
    """Argument vector shared by UI and legacy callers; no shell interpretation."""
    options = TransferOptions(track_renames=track_renames, bw_limit=bw_limit, copy_links=copy_links, excludes=excludes)
    arguments = [str(rclone_path), '--config', str(config_path), 'sync', '--create-empty-src-dirs']
    if integrated:
        # Leave rclone's retry policy untouched; observe its own retry messages.
        arguments += ['--use-json-log', '--stats', '1s', '--stats-log-level', 'NOTICE']
    else:
        arguments += ['--progress']
    arguments += ['--transfers=1' if '-VM' in str(source_path) else '--transfers=10']
    if dry_run:
        arguments += ['--dry-run']
    arguments += options.cli_arguments()
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
