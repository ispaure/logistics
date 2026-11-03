"""Desktop crypt commands bound to one private credential session.

Both path encoding and document I/O use the same revocation/cancellation gate.
Only child process environments carry decoded settings; no config is written.
"""
import json
import os

from commonUtils.integrations.wrappers.cmdShellWrapper.binary import run_bytes
from commonUtils.runtime.operations import check_cancelled
from features.rclone import session
from .path_batches import map_path_entries


class CryptCommand:
    def __init__(self, binary, context, cancellation, validate, *, closed, remote='view'):
        self.binary = binary
        self.context = context
        self.cancellation = cancellation
        self.validate = validate
        self.closed = closed
        self.remote = remote

    def _run(self, arguments, path, *, limit, cancelled=lambda: False,
             input_data=None, input_writer=None):
        self.validate()
        scoped = self.cancellation.current
        revoked = session.revocation_check(self.context)

        def stopped():
            return self.closed() or revoked() or scoped() or cancelled()

        check_cancelled(stopped)
        launched = session.launch(self.context, self.remote + ':' + path, '')
        if launched is None:
            raise ValueError('The credential session is locked. Reopen the document after unlocking its ZIP.')
        environment, remote, _ = launched
        command = [str(self.binary), '--config', session.NULL_CONFIG, *arguments(remote)]
        result = run_bytes(command, environment=environment, input_data=input_data,
                           input_writer=input_writer, max_output=limit, cancelled=stopped)
        self.validate()
        check_cancelled(stopped)
        return result

    def command(self, operation, path, *extra, input_data=None, input_writer=None,
                limit=1024 * 1024, cancelled=lambda: False):
        def arguments(remote):
            return ['--log-level', 'ERROR', '--retries', '1', '--low-level-retries', '1',
                    '--contimeout', '15s', '--timeout', '30s', operation, remote, *extra]
        return self._run(arguments, path, limit=limit, cancelled=cancelled,
                         input_data=input_data, input_writer=input_writer)

    def encode_many(self, relatives):
        return self._map_many('encode', relatives)

    def decode_many(self, relatives):
        return self._map_many('decode', relatives)

    def _map_many(self, operation, relatives):
        def resolve(batch):
            paths = [path for path, _ in batch]
            result = self._run(lambda remote: ['backend', operation, remote, '--json', '--', *paths],
                               '', limit=2 * 1024 * 1024)
            return json.loads(result)
        # Keep Windows command lines below its 32 KiB limit. POSIX hosts can
        # amortize process/crypt initialization across larger bounded batches.
        return map_path_entries(((path, False) for path in relatives), resolve, check=self.validate,
                                batch_size=512 if os.name != 'nt' else 128,
                                max_bytes=64 * 1024 if os.name != 'nt' else 24 * 1024)

    def encode(self, relative):
        return self.encode_many([relative])[0]
