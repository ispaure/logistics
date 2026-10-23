"""Desktop crypt commands bound to one private credential session.

Both path encoding and document I/O use the same revocation/cancellation gate.
Only child process environments carry decoded settings; no config is written.
"""
import json

from commonUtils.integrations.wrappers.cmdShellWrapper.binary import run_bytes
from commonUtils.runtime.operations import check_cancelled
from features.rclone import session


class CryptCommand:
    def __init__(self, binary, context, cancellation, validate, *, closed):
        self.binary = binary
        self.context = context
        self.cancellation = cancellation
        self.validate = validate
        self.closed = closed

    def _run(self, arguments, path, *, limit, cancelled=lambda: False,
             input_data=None, input_writer=None):
        self.validate()
        scoped = self.cancellation.current
        revoked = session.revocation_check(self.context)

        def stopped():
            return self.closed() or revoked() or scoped() or cancelled()

        check_cancelled(stopped)
        launched = session.launch(self.context, 'view:' + path, '')
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

    def encode(self, relative):
        result = self._run(lambda remote: ['backend', 'encode', remote, relative, '--json'],
                           '', limit=16384)
        paths = json.loads(result)
        if not isinstance(paths, list) or len(paths) != 1 or not isinstance(paths[0], str):
            raise ValueError('Encrypted path could not be resolved.')
        return paths[0]
