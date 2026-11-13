"""Read a reMarkable document store over OpenSSH and package one native archive."""
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
from tempfile import NamedTemporaryFile, TemporaryDirectory, TemporaryFile
from threading import Event, Thread
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


@contextmanager
def ssh_stream(host, command, cancelled, *, port=DEFAULT_PORT):
    host = host.strip()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.:-]{0,252}', host):
        raise ValueError('Enter the tablet IP address or an SSH host name.')
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Enter an SSH port between 1 and 65535.')
    ssh = shutil.which('ssh')
    if ssh is None:
        raise OSError('OpenSSH is required to connect to the tablet.')
    check_cancelled(cancelled)
    with TemporaryDirectory(prefix='logistics-ssh-') as temporary, TemporaryFile() as errors:
        env = os.environ.copy()
        env.pop('SSH_ASKPASS_PROMPT', None)
        if sys.platform == 'darwin' and not env.get('SSH_ASKPASS'):
            with NamedTemporaryFile(dir=temporary, delete=False) as helper:
                helper.write(MAC_ASKPASS.encode())
                os.fchmod(helper.fileno(), 0o700)
            env['SSH_ASKPASS'] = helper.name
        interactive = bool(env.get('SSH_ASKPASS'))
        if interactive:
            env['SSH_ASKPASS_REQUIRE'] = 'force'
        args = [ssh, '-T', '-p', str(port), '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=10',
                '-o', 'ServerAliveCountMax=3', '-o', 'ClearAllForwardings=yes', '-o', 'ForwardAgent=no',
                '-o', 'ControlMaster=no', '-o', 'ControlPath=none',
                '-o', 'PermitLocalCommand=no', '-o', 'NumberOfPasswordPrompts=1',
                '-o', 'StrictHostKeyChecking=' + ('ask' if interactive else 'yes'),
                '-o', 'BatchMode=' + ('no' if interactive else 'yes'), '--', TABLET_USER + '@' + host, STORE + command]
        grouped = os.name != 'nt'
        with subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=errors, env=env, start_new_session=grouped) as process:
            finished = Event()

            def stop():
                with suppress(ProcessLookupError):
                    if grouped:
                        os.killpg(process.pid, signal.SIGKILL)
                    elif process.poll() is None:
                        process.kill()

            def watch():
                while not finished.wait(.1):
                    if cancelled():
                        stop()
                        return

            watcher = Thread(target=watch, daemon=True)
            watcher.start()
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
            finally:
                finished.set()
                watcher.join()
                if process.poll() is None:
                    stop()


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


def list_metadata(host, cancelled=lambda: False, *, port=DEFAULT_PORT):
    """Read native IDs and metadata without changing the tablet store."""
    command = '''set -- ./*.metadata
if [ -f "$1" ]; then exec tar -cf - "$@"; fi'''
    entries = {}
    with ssh_stream(host, command, cancelled, port=port) as stream:
        if stream.peek(1):
            with tarfile.open(fileobj=stream, mode='r|') as archive:
                for member in archive:
                    check_cancelled(cancelled)
                    name = PurePosixPath(member.name)
                    if not member.isfile() or len(name.parts) != 1 or name.suffix != '.metadata' or not UUID.fullmatch(name.stem):
                        continue
                    with archive.extractfile(member) as metadata:
                        try:
                            entries[name.stem] = _json_member(metadata, member.size)
                        except ValueError:
                            continue
    return entries


def list_snapshot(host, cancelled=lambda: False, *, port=DEFAULT_PORT):
    from .remarkable_store import TabletSnapshot
    return TabletSnapshot.from_metadata(list_metadata(host, cancelled, port=port), cancelled=cancelled)


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
                    report=lambda *_: None, cancelled=lambda: False):
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
    with stage_local_document_export(destination, expected_revision=expected_revision, cancelled=cancelled) as target:
        with ssh_stream(host, command, cancelled, port=port) as stream, \
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
