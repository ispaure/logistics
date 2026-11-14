"""Trusted OpenSSH transport and byte-preserving native document retrieval."""
from contextlib import contextmanager, suppress
from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import time
from tempfile import NamedTemporaryFile, TemporaryDirectory, TemporaryFile
from threading import Event, Lock, Thread
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.streams import iter_chunks
from services.documents.storage import stage_local_document_export

DEFAULT_HOST = '10.11.99.1'
DEFAULT_PORT = 22
TABLET_USER = 'root'
STORE = 'cd /home/root/.local/share/remarkable/xochitl || exit 1\n'
UUID = re.compile(r'[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}')
MAX_SIDECAR = 16 * 1024 * 1024
MAX_SCOPED_SIDECARS = 64 * 1024 * 1024

MAC_ASKPASS = """#!/bin/sh
[ "${SSH_ASKPASS_PROMPT:-}" != none ] || exit 0
exec /usr/bin/osascript - "$1" "${SSH_ASKPASS_PROMPT:-}" <<'APPLESCRIPT'
on run argv
    set promptText to item 1 of argv
    if item 2 of argv is "confirm" or promptText contains "(yes/no" then
        display dialog promptText with title "Logistics SSH" buttons {"Cancel", "Trust"} default button "Cancel" cancel button "Cancel"
        return "yes"
    end if
    return text returned of (display dialog promptText with title "Logistics SSH" default answer "" with hidden answer)
end run
APPLESCRIPT
"""


def _ssh_settings(host, port, temporary, *, control_path='none', master=False, batch_only=False):
    host = host.strip()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.:-]{0,252}', host):
        raise ValueError('Enter the tablet IP address or an SSH host name.')
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Enter an SSH port between 1 and 65535.')
    ssh = shutil.which('ssh')
    if ssh is None:
        raise OSError('OpenSSH is required to connect to the tablet.')
    env = os.environ.copy()
    env.pop('SSH_ASKPASS_PROMPT', None)
    if not batch_only and sys.platform == 'darwin' and not env.get('SSH_ASKPASS'):
        with NamedTemporaryFile(dir=temporary, delete=False) as helper:
            helper.write(MAC_ASKPASS.encode())
            os.fchmod(helper.fileno(), 0o700)
        env['SSH_ASKPASS'] = helper.name
    interactive = bool(env.get('SSH_ASKPASS')) and not batch_only
    if interactive:
        env['SSH_ASKPASS_REQUIRE'] = 'force'
    args = [ssh, '-T', '-p', str(port), '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=10',
            '-o', 'ServerAliveCountMax=3', '-o', 'ClearAllForwardings=yes', '-o', 'ForwardAgent=no',
            '-o', 'ControlMaster=' + ('yes' if master else 'no'), '-o', 'ControlPath=' + str(control_path),
            '-o', 'PermitLocalCommand=no', '-o', 'NumberOfPasswordPrompts=1',
            '-o', 'StrictHostKeyChecking=' + ('ask' if interactive else 'yes'),
            '-o', 'BatchMode=' + ('no' if interactive else 'yes')]
    if master:
        args.append('-N')
    elif control_path != 'none':
        # Multiplexed clients must not silently open another authenticated
        # connection if their owned master disappears between check and exec.
        args += ['-o', 'ProxyCommand=false']
    args += ['--', TABLET_USER + '@' + host]
    return args, env


class SSHConnection:
    """One context-owned authenticated connection; no global control sockets."""
    def __init__(self, host, port, socket, process):
        self.host, self.port, self.socket, self.process = host, port, socket, process

    def check(self, host, port):
        if (host.strip(), port) != (self.host, self.port):
            raise ValueError('The SSH connection belongs to a different tablet endpoint.')
        if self.process.poll() is not None or not self.socket.exists():
            raise OSError('The tablet connection closed; reconnect before continuing.')


def _stop_process(process, *, grouped):
    if process.poll() is not None:
        return
    try:
        if grouped:
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        pass
    except PermissionError:
        # Some hosts report EPERM for a group that exited between poll/kill.
        if process.poll() is None:
            raise


@contextmanager
def ssh_connection(host, cancelled=lambda: False, *, port=DEFAULT_PORT, timeout=90):
    """Authenticate once for a bounded batch and retire the owned master on exit."""
    if os.name != 'posix':
        raise OSError('Reusable SSH sessions require a POSIX OpenSSH host.')
    if not isinstance(timeout, (int, float)) or not 0 < timeout <= 300:
        raise ValueError('Choose an SSH login timeout between zero and 300 seconds.')
    check_cancelled(cancelled)
    # Unix control sockets have a small path limit. The user's normal temporary
    # directory (or a managed test workspace) can already exceed that limit.
    with TemporaryDirectory(prefix='logistics-ssh-', dir='/tmp') as temporary, TemporaryFile() as errors:
        socket = Path(temporary) / 'control'
        args, env = _ssh_settings(host, port, temporary, control_path=socket, master=True)
        with subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=errors, env=env, start_new_session=os.name != 'nt') as process:
            try:
                deadline = time.monotonic() + timeout
                while not socket.exists():
                    check_cancelled(cancelled)
                    if process.poll() is not None:
                        errors.seek(0)
                        raise OSError(errors.read(4096).decode(errors='replace').strip() or 'SSH authentication failed.')
                    if time.monotonic() >= deadline:
                        raise TimeoutError('The SSH login did not finish in time.')
                    time.sleep(.05)
                connection = SSHConnection(host.strip(), port, socket, process)
                connection.check(host, port)
                check_cancelled(cancelled)
                yield connection
            finally:
                if process.poll() is None and socket.exists():
                    with suppress(OSError, subprocess.TimeoutExpired):
                        subprocess.run([args[0], '-p', str(port), '-S', str(socket), '-O', 'exit',
                                        '--', TABLET_USER + '@' + host.strip()], stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                    with suppress(subprocess.TimeoutExpired):
                        process.wait(timeout=5)
                # Also terminate an askpass child if login was cancelled or the
                # timeout expired before authentication created its socket.
                _stop_process(process, grouped=True)
                process.wait()


@contextmanager
def ssh_stream(host, command, cancelled, *, port=DEFAULT_PORT, connection=None, input_data=None):
    if input_data is not None and not isinstance(input_data, bytes):
        raise TypeError('SSH input must be immutable bytes.')
    check_cancelled(cancelled)
    if connection is not None:
        connection.check(host, port)
    with TemporaryDirectory(prefix='logistics-ssh-') as temporary, TemporaryFile() as errors:
        args, env = _ssh_settings(host, port, temporary,
                                 control_path=connection.socket if connection else 'none', batch_only=connection is not None)
        args.append(STORE + command)
        grouped = os.name != 'nt'
        with subprocess.Popen(args, stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=errors, env=env, start_new_session=grouped) as process:
            finished = Event()
            stop_lock = Lock()
            stop_requested = False

            def stop():
                nonlocal stop_requested
                with stop_lock:
                    if not stop_requested:
                        _stop_process(process, grouped=grouped)
                        stop_requested = True

            def watch():
                while not finished.wait(.1):
                    if cancelled():
                        stop()
                        return

            watcher = Thread(target=watch, daemon=True)
            watcher.start()
            input_errors = []

            def send():
                try:
                    with process.stdin:
                        for offset in range(0, len(input_data), 256 * 1024):
                            check_cancelled(cancelled)
                            process.stdin.write(input_data[offset:offset + 256 * 1024])
                except Exception as error:
                    input_errors.append(error)

            sender = Thread(target=send, daemon=True) if input_data is not None else None
            if sender is not None:
                sender.start()
            try:
                stream_error = None
                try:
                    yield process.stdout
                except tarfile.ReadError as error:
                    stream_error = error
                # The tar reader stops at the end marker. Drain padding and
                # wait for SSH so a remote read failure cannot publish a copy.
                for _ in iter_chunks(process.stdout, cancelled=cancelled):
                    pass
                code = process.wait()
                check_cancelled(cancelled)
                if code:
                    errors.seek(0)
                    detail = errors.read(4096).decode(errors='replace').strip()
                    raise OSError(detail or f'SSH failed with exit code {code}.')
                if stream_error is not None:
                    raise stream_error
                if sender is not None:
                    sender.join()
                    if input_errors:
                        raise input_errors[0]
            finally:
                finished.set()
                watcher.join()
                if process.poll() is None:
                    stop()
                if sender is not None:
                    sender.join()


@dataclass(frozen=True)
class TabletDocument:
    id: str
    title: str
    folder: str


def _json_member(stream, size):
    if size > MAX_SIDECAR:
        raise ValueError('A tablet metadata entry is too large.')
    value = json.loads(stream.read())
    if not isinstance(value, dict):
        raise ValueError('Invalid tablet document metadata.')
    return value


def read_sidecars(host, identities, cancelled=lambda: False, *, port=DEFAULT_PORT, connection=None):
    """Read exact-ID raw metadata/content without enumerating the document store.

    Metadata is required; content is optional (including for collections). This
    is a revision source, not a writer lock or a consistent firmware snapshot.
    """
    identities = tuple(identities)
    if (not 1 <= len(identities) <= 256
            or any(not isinstance(key, str) or not UUID.fullmatch(key) for key in identities)
            or len(set(identities)) != len(identities)):
        raise ValueError('Choose between one and 256 distinct native IDs.')
    required = {key + '.metadata' for key in identities}
    allowed = required | {key + '.content' for key in identities}
    command = 'set --\n'
    command += 'for identity in ' + ' '.join(identities) + '; do\n'
    command += '''    if [ ! -f "$identity.metadata" ] || [ -L "$identity.metadata" ]; then
        echo 'A selected native record is missing or unsupported; refresh before continuing.' >&2
        exit 1
    fi
    set -- "$@" "$identity.metadata"
    if [ -e "$identity.content" ] || [ -L "$identity.content" ]; then
        set -- "$@" "$identity.content"
    fi
done
exec tar --no-recursion -cf - "$@"'''
    result = {}
    total = 0
    with ssh_stream(host, command, cancelled, port=port, connection=connection) as stream:
        with tarfile.open(fileobj=stream, mode='r|') as archive:
            for member in archive:
                check_cancelled(cancelled)
                total += member.size
                if (member.name not in allowed or member.name in result or not member.isfile()
                        or not 0 <= member.size <= MAX_SIDECAR or total > MAX_SCOPED_SIDECARS):
                    raise ValueError('The scoped native sidecar response is invalid.')
                with archive.extractfile(member) as source:
                    data = b''.join(iter_chunks(source, cancelled=cancelled))
                if len(data) != member.size:
                    raise ValueError('The scoped native sidecar response is incomplete.')
                result[member.name] = data
    if not required <= result.keys():
        raise ValueError('Selected native metadata is missing; refresh before continuing.')
    return result


def _read_metadata(host, cancelled, *, port):
    command = '''set -- ./*.metadata
if [ -e "$1" ] || [ -L "$1" ]; then exec tar --no-recursion -cf - "$@"; fi'''
    entries = {}
    observations = []
    with ssh_stream(host, command, cancelled, port=port) as stream:
        if stream.peek(1):
            with tarfile.open(fileobj=stream, mode='r|') as archive:
                for member in archive:
                    check_cancelled(cancelled)
                    name = PurePosixPath(member.name)
                    if len(name.parts) != 1 or name.suffix != '.metadata' or not UUID.fullmatch(name.stem):
                        observations.append(('', 'unidentified_entry'))
                        continue
                    identity = name.stem
                    if not member.isfile():
                        observations.append((identity, 'unsupported_entry'))
                        continue
                    if member.size > MAX_SIDECAR:
                        observations.append((identity, 'metadata_too_large'))
                        continue
                    with archive.extractfile(member) as metadata:
                        try:
                            entries[identity] = _json_member(metadata, member.size)
                        except (ValueError, RecursionError):
                            observations.append((identity, 'unreadable_metadata'))
                            continue
                    observations.append((identity, 'read'))
    return entries, observations


def list_metadata(host, cancelled=lambda: False, *, port=DEFAULT_PORT):
    """Read native IDs and metadata; use list_snapshot for an omission receipt."""
    return _read_metadata(host, cancelled, port=port)[0]


def list_snapshot(host, cancelled=lambda: False, *, port=DEFAULT_PORT):
    from .remarkable_store import TabletSnapshot
    metadata, observations = _read_metadata(host, cancelled, port=port)
    return TabletSnapshot.from_metadata(metadata, observations=observations, cancelled=cancelled)


def list_documents(host, cancelled=lambda: False, *, port=DEFAULT_PORT):
    """Compatibility enumeration: keep the established flattened retrieval API."""
    entries = list_metadata(host, cancelled, port=port)

    def folder_name(entry):
        labels = []
        seen = set()
        parent = entry.get('parent')
        while isinstance(parent, str) and parent:
            if parent == 'trash':
                return None
            if parent in seen or parent not in entries:
                break
            seen.add(parent)
            folder = entries[parent]
            if folder.get('deleted'):
                return None
            labels.append(str(folder.get('visibleName') or 'Untitled folder'))
            parent = folder.get('parent')
        return ' / '.join(reversed(labels))

    result = []
    for identity, entry in entries.items():
        if entry.get('type') == 'DocumentType' and not entry.get('deleted'):
            folder = folder_name(entry)
            if folder is not None:
                result.append(TabletDocument(identity, str(entry.get('visibleName') or 'Untitled'), folder))
    return sorted(result, key=lambda item: (item.folder.casefold(), item.title.casefold(), item.id))


def export_document(host, identity, destination, *, port=DEFAULT_PORT, expected_revision=None,
                    report=lambda *_: None, cancelled=lambda: False, connection=None):
    """Retrieve a complete archive; replacing a local file requires its approved revision."""
    if not UUID.fullmatch(identity):
        raise ValueError('Invalid tablet document ID.')
    destination = Path(destination)
    command = f'''identity='{identity}'
set --
for item in "$identity" "$identity".*; do
    if [ -e "$item" ]; then set -- "$@" "$item"; fi
done
if [ ! -f "$identity.metadata" ] || [ ! -f "$identity.content" ]; then
    echo 'The selected document is missing from the tablet store. Reconnect to refresh the list.' >&2
    exit 1
fi
exec tar -cf - "$@"'''
    session = {'connection': connection} if connection is not None else {}
    with stage_local_document_export(destination, expected_revision=expected_revision, cancelled=cancelled) as target:
        with ssh_stream(host, command, cancelled, port=port, **session) as stream, \
                tarfile.open(fileobj=stream, mode='r|') as source, \
                ZipFile(target, 'w') as archive:
            names = set()
            total = 0
            for member in source:
                check_cancelled(cancelled)
                name = member.name
                path = PurePosixPath(name)
                if (path.is_absolute() or path.as_posix() != name or '\\' in name or ':' in name
                        or '..' in path.parts or not path.parts
                        or not (path.parts[0] == identity or path.parts[0].startswith(identity + '.'))):
                    raise ValueError('The tablet returned an invalid archive path.')
                if member.isdir():
                    continue
                if not member.isfile() or name in names:
                    raise ValueError('The tablet returned a duplicate or unsupported archive entry.')
                names.add(name)
                entry = ZipInfo(name)
                entry.compress_type = ZIP_DEFLATED
                entry.file_size = member.size
                with source.extractfile(member) as content, archive.open(entry, 'w') as output:
                    for chunk in iter_chunks(content, cancelled=cancelled):
                        output.write(chunk)
                        total += len(chunk)
                        report(total, 0, f'Retrieving notebook… {total // (1024 * 1024)} MiB')

        report(0, 0, 'Verifying archive…')
        target.seek(0)
        with ZipFile(target) as archive:
            for suffix in ('.metadata', '.content'):
                member = archive.getinfo(identity + suffix)
                with archive.open(member) as entry:
                    metadata = _json_member(entry, member.file_size)
                if suffix == '.content':
                    kind = metadata.get('fileType')
                    if kind in ('pdf', 'epub'):
                        archive.getinfo(f'{identity}.{kind}')
            for member in archive.infolist():
                with archive.open(member) as entry:
                    for _ in iter_chunks(entry, cancelled=cancelled):
                        pass  # Reading to EOF verifies each member's CRC.
    return destination
