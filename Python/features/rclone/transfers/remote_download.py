"""Download one desktop remote item and publish it to an ordinary local folder."""

import json
from pathlib import Path
from queue import Empty, Queue
import subprocess
from tempfile import TemporaryDirectory

from commonUtils.filesystem.local_access import check_local_path
from commonUtils.filesystem.transfers import validate_name
from commonUtils.integrations.wrappers.cmdShellWrapper.binary import BinaryCommandError
from commonUtils.integrations.wrappers.cmdShellWrapper.output import read_stream
from commonUtils.integrations.wrappers.cmdShellWrapper.process import ProcessSupervisor, get_process_group_kwargs
from commonUtils.persistence.publication import rename_exclusive
from commonUtils.runtime.platform.capabilities import Capability, require_capability
from commonUtils.runtime.operations import check_cancelled
from features.rclone import session
from features.rclone.remote_resources import remote_failure


def _copy(arguments, environment, check, progress):
    require_capability(Capability.SUBPROCESS, 'remote download')
    check()
    child = subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.PIPE, env=environment, **get_process_group_kwargs())
    events = Queue()
    pending = b''
    diagnostics = bytearray()
    reading = True
    with ProcessSupervisor(child) as supervisor:
        reader = supervisor.start(read_stream, args=(child.stderr, 'stderr', events))
        while reading or child.poll() is None:
            check()
            try:
                _, chunk = events.get(timeout=.05)
            except Empty:
                continue
            if chunk is None:
                reading = False
                continue
            if isinstance(chunk, Exception):
                raise chunk
            lines = (pending + chunk).split(b'\n')
            pending = lines.pop()[-1024 * 1024:]
            for line in lines:
                try:
                    record = json.loads(line)
                except (ValueError, UnicodeError):
                    record = None
                stats = record.get('stats') if isinstance(record, dict) else None
                if isinstance(stats, dict):
                    # rclone errors can contain credentials and staging paths.
                    stats.pop('lastError', None)
                    progress(stats)
                else:
                    diagnostics.extend(line + b'\n')
                    diagnostics = diagnostics[-65536:]
        reader.join()
        check()
        if child.returncode:
            error = BinaryCommandError(child.returncode, (diagnostics + pending)[-65536:])
            raise OSError(remote_failure(error))


def download_remote_item(provider, path, destination, *, cancelled, progress=lambda _stats: None):
    """Use the browser's credential generation throughout the staged transfer."""
    relative = provider.relative(path)
    if not relative:
        raise ValueError('Choose a file or folder in the remote browser.')
    destination = Path(destination)
    validate_name(destination.name)
    destination = destination.parent.resolve(strict=True) / destination.name
    check_local_path(destination, recursive=True)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('An item with that name already exists. Choose another name.')

    with provider.operation(cancelled):
        directory = provider.entry(relative)['directory']
        launched = session.launch(provider.context, f'{provider.remote}:{relative}', '')
        if launched is None:
            raise ValueError('The remote credential session has ended. Reopen this remote.')
        environment, source, _ = launched
        with TemporaryDirectory(prefix='.logistics-download-', dir=destination.parent) as temporary:
            staged = Path(temporary) / 'item'
            command = ['copy', '--create-empty-src-dirs'] if directory else ['copyto']
            _copy([str(provider.binary), '--config', session.NULL_CONFIG,
                '--log-level', 'ERROR', '--use-json-log', '--stats', '1s', '--stats-log-level', 'ERROR',
                *command, '--', source, str(staged)], environment, provider.check, progress)
            provider.check()
            if not (staged.is_dir() if directory else staged.is_file()):
                raise OSError('The remote download did not produce the selected item.')
            if provider.entry(relative)['directory'] != directory:
                raise ValueError('The selected item changed during the download. Select it again.')
            check_local_path(destination, recursive=True)
            check_cancelled(cancelled)
            provider.check()
            try:
                rename_exclusive(staged, destination)
            except FileExistsError:
                raise FileExistsError('An item with that name already exists. Choose another name.') from None
    return destination
