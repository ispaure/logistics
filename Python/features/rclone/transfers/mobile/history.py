"""Persist completed transfers under the same credential boundary as their downloads."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from dataclasses import dataclass
import json
from pathlib import Path
from time import time_ns
from typing import Callable

from commonUtils.persistence import atomic_write_bytes
from commonUtils.persistence.locking import file_lock
from features.rclone.mobile.download_recovery import SavedTransferCipher, download_origins, mobile_queue
from features.rclone.mobile.service import native_service
from features.rclone.remote_access import NativeRemoteLocation
from features.rclone.transfers.download_recovery import RestartRequired


HISTORY_LIMIT = 60
# Session-only records use the same 128 KiB plaintext limit as credential document lists.
RECORD_LIMIT = 128 * 1024


@dataclass(frozen=True)
class TransferHistory:
    path: Path
    cipher: object
    check: Callable[[], None]

    def validate(self):
        self.check()
        if any(path.is_symlink() for path in (self.path, self.path.parent)):
            raise ValueError('Linked transfer history cannot be opened.')

    def rows(self):
        self.validate()
        try:
            with self.path.open('rb') as stream:
                sealed = stream.read(RECORD_LIMIT + 1025)
        except FileNotFoundError:
            return []
        if len(sealed) > RECORD_LIMIT + 1024:
            raise ValueError('Transfer history is too large.')
        contents = json.loads(self.cipher.transform(sealed, True))
        if not isinstance(contents, dict) or contents.get('scope') != self.path.stem:
            raise ValueError('Invalid transfer history scope.')
        data = contents.get('rows')
        if (not isinstance(data, list) or len(data) > HISTORY_LIMIT or not all(
                isinstance(row, dict) and type(row.get('time')) is int and row['time'] > 0
                and row.get('operation') in ('download', 'pull', 'push')
                and isinstance(row.get('source'), str) and isinstance(row.get('destination'), str)
                and type(row.get('bytes')) is int and row['bytes'] >= 0 for row in data)):
            raise ValueError('Invalid transfer history.')
        self.validate()
        return data

    def update(self, update_rows):
        self.validate()
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock = self.path.with_suffix('.lock')
        if lock.is_symlink():
            raise ValueError('Linked transfer history lock.')
        with file_lock(lock, timeout=2) as acquired:
            if not acquired:
                raise OSError('Transfer history is busy. Try again.')
            previous = self.rows()
            rows = update_rows(previous)
            if rows != previous:
                def encode():
                    return json.dumps(dict(scope=self.path.stem, rows=rows), ensure_ascii=False).encode()

                data = encode()
                while len(data) > RECORD_LIMIT:
                    rows.pop()
                    data = encode()
                atomic_write_bytes(self.path, self.cipher.transform(data), validate=self.validate, file_mode=0o600)


def saved_history(root, client, check):
    return TransferHistory(Path(root) / 'TransferHistory' / 'saved.bin',
                           SavedTransferCipher(client, 'completed transfer history v1'), check)


def session_history(root, source):
    queue = mobile_queue(root, source)
    return TransferHistory(Path(root) / 'TransferHistory' / (queue.authority + '.bin'), queue.cipher, queue.validate)


def credential_check(client, generation):
    if client.generation != generation:
        raise PermissionError('The connection changed.')


def record_completed(root, client, generation, remote, identity, operation, source, destination, size):
    def check():
        credential_check(client, generation)

    check()
    record = next((record for record in getattr(client, 'package_records', ())
                   if record.get('identities', {}).get(remote) == identity), None)
    if record is None:
        return
    row = dict(time=time_ns(), operation=operation, source=source[:256], destination=destination[:256],
               bytes=max(0, int(size)))

    def append(history):
        history.update(lambda rows: [row, *rows][:HISTORY_LIMIT])

    if record['saved']:
        append(saved_history(root, client, check))
    else:
        provider = native_service(client).remotes.open(NativeRemoteLocation(remote, identity, generation))
        try:
            try:
                history = session_history(root, provider)
            except RestartRequired:
                return  # A passwordless session has no persistent encryption key.
            append(history)
        finally:
            provider.close()


def visible_history(root, client, generation, *, clear_through=None):
    if client is None or not (Path(root) / 'TransferHistory').exists():
        return []

    def check():
        credential_check(client, generation)

    check()
    saved = saved_history(root, client, check)

    def read(history):
        if clear_through is not None and history.path.exists():
            history.update(lambda rows: [row for row in rows if row['time'] > clear_through])
        return history.rows()

    rows = read(saved)
    for origin in download_origins(client, saved=False):
        provider = native_service(client).remotes.open(origin)
        try:
            try:
                history = session_history(root, provider)
            except RestartRequired:
                continue
            rows.extend(read(history))
        finally:
            provider.close()
    check()
    return sorted(rows, key=lambda row: row['time'], reverse=True)[:HISTORY_LIMIT]
