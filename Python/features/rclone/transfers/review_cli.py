"""Read-only rclone dry-run comparison adapter; no report files on disk."""
from hashlib import sha256
import json
import re
from pathlib import Path
import subprocess
from threading import Thread

from features.rclone.transfers.review import replace_changes
from features.rclone import session
from features.rclone.transfers.transfer_options import TransferOptions


def _lines(arguments, environment, cancelled, consume):
    # The watchdog also interrupts a child which is blocked on remote I/O and
    # has not emitted another line. Always reap it before retiring the scanner.
    with subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, env=environment) as process:
        from threading import Event
        done = Event()
        def watch():
            while not done.wait(.05):
                if cancelled():
                    try:
                        process.terminate()
                    except ProcessLookupError:
                        return
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    return
        watcher = Thread(target=watch, daemon=True)
        watcher.start()
        try:
            for line in process.stdout:
                if cancelled():
                    break
                consume(line)
            if process.wait() and not cancelled():
                raise ValueError('rclone comparison failed. Check the connection and retry.')
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            done.set()
            watcher.join()


def scanner(binary, source, destination, config_path, options=TransferOptions(), *,
            display_path=lambda path, cancelled: path, display_directory=None, cleanup_plan=lambda cancelled: {}):
    def scan(emit, cancelled):
        revoked = session.revocation_check(config_path)
        launched = session.launch(config_path, source, destination)
        environment = None
        src, dst, config = str(source), str(destination), str(config_path)
        if launched is not None:
            requested = cancelled
            cancelled = lambda: requested() or revoked()
            values, src, dst = launched
            environment = values
            config = session.NULL_CONFIG
        elif Path(config_path).suffix == '.session':
            raise ValueError('This credential session has ended. Unlock the package again.')
        if cancelled():
            return ''
        digest = sha256()
        cleanup = cleanup_plan(cancelled)
        digest.update(json.dumps(cleanup, sort_keys=True).encode())
        changes = {}
        def record_change(kind, path):
            changes[path] = (kind, path)
            emit(kind, path)
        sigils = {'+': 'add', '*': 'replace', '-': 'delete', '=': 'match'}
        def comparison(line):
            try:
                record = json.loads(line)
            except (ValueError, UnicodeError):
                return  # The combined stdout report is redundant with JSON.
            message = record.get('msg', '') if isinstance(record, dict) else ''
            if re.match(r'^Attempt \d+/\d+ failed with', message):
                changes.clear()
                replace_changes(emit, ())
            if message.startswith('Sync Logger: '):
                parts = message.split(': ', 2)
                if len(parts) == 3 and len(parts[2]) >= 2:
                    code, path = parts[2][0], parts[2][2:].removesuffix('\n')
                    if code in sigils:
                        if path in cleanup:
                            # Cleanup removes this source file before real Sync.
                            # A destination copy therefore becomes a deletion;
                            # a source-only addition will never be uploaded.
                            if code != '+':
                                record_change('delete', cleanup[path][0])
                        else:
                            record_change(sigils[code], display_path(path, cancelled))
        flags = options.cli_arguments()
        arguments = [str(binary), 'sync', '--config', config, '--dry-run', '--combined', '-',
                     '--use-json-log', '--log-level', 'DEBUG', '--create-empty-src-dirs', *flags, '--', src, dst]
        _lines(arguments, environment, cancelled, comparison)
        if cancelled():
            return ''
        replace_changes(emit, [*changes.values(), *[('cleanup', label) for label, _ in cleanup.values()]])
        # Record both trees for stale-review detection, including matching files.
        # Metadata is streamed to RAM, never written to plaintext report files.
        trees = []
        for target in (src, dst):
            chunks = []
            def inventory(line):
                chunks.append(line)
            # lsjson of a nonexistent new Local destination is an empty tree.
            if Path(target).is_absolute() and not Path(target).exists():
                rows = []
            else:
                _lines([str(binary), 'lsjson', target, '--config', config, '-R', '--no-mimetype',
                        *(['--copy-links'] if options.copy_links else []),
                        *[argument for pattern in options.excludes for argument in ('--exclude', pattern)]],
                       environment, cancelled, inventory)
                if cancelled():
                    return ''
                rows = json.loads(b''.join(chunks))
            # Directory mtimes/sizes/IDs vary between backends and with child
            # writes. Review membership/type; retain file metadata for revisions.
            rows = [dict(Path=row['Path'], IsDir=True) if row['IsDir'] else row for row in rows]
            trees.append({row['Path']: row for row in rows})
            digest.update(json.dumps(sorted(rows, key=lambda row: row['Path']), sort_keys=True,
                                     separators=(',', ':')).encode())
        source_tree, destination_tree = trees
        directory_label = display_directory or display_path
        for name in sorted(source_tree.keys() | destination_tree.keys()):
            source_dir = source_tree.get(name, {}).get('IsDir', False)
            destination_dir = destination_tree.get(name, {}).get('IsDir', False)
            if source_dir or destination_dir:
                kind = 'match' if source_dir and destination_dir else 'add' if source_dir else 'delete'
                record_change(kind, directory_label(name, cancelled) + '/')
        replace_changes(emit, [*changes.values(), *[('cleanup', label) for label, _ in cleanup.values()]])
        return '' if cancelled() else digest.hexdigest()
    return scan
