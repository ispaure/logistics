"""Exercise owned SSH processes without a server or any tablet access."""
from hashlib import sha256
import json
import os
from pathlib import Path
import signal
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.runtime.operations import OperationCancelled
from commonUtils.testing.stages import TestStage
from features.notebooks import remarkable_ssh as ssh

TEST_STAGE = TestStage.REGRESSION

FAKE_SSH = r'''
import hashlib, json, os, pathlib, sys, time
args = sys.argv[1:]
with open(os.environ['LQA_SSH_LOG'], 'a') as log:
    log.write(json.dumps(args) + '\n')
socket = next((arg.split('=', 1)[1] for arg in args if arg.startswith('ControlPath=')), None)
if '-O' in args:
    pathlib.Path(args[args.index('-S') + 1]).unlink(missing_ok=True)
elif '-N' in args:
    mode = os.environ.get('LQA_SSH_MODE', '')
    if mode == 'reject':
        sys.stderr.write('Synthetic authentication failed')
        sys.exit(255)
    if mode == 'wait':
        time.sleep(60)
    pathlib.Path(socket).touch()
    while pathlib.Path(socket).exists():
        time.sleep(.02)
elif args[-1].endswith('wait'):
    time.sleep(60)
elif args[-1].endswith('early'):
    pass
else:
    data = sys.stdin.buffer.read()
    sys.stdout.write(hashlib.sha256(data).hexdigest())
'''


@unittest.skipUnless(os.name == 'posix', 'Owned OpenSSH multiplexing uses POSIX processes.')
class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        executable = self.root / 'ssh'
        executable.write_text('#!' + sys.executable + '\n' + FAKE_SSH)
        executable.chmod(0o700)
        self.log = self.root / 'calls.jsonl'
        for patcher in (patch.object(ssh.shutil, 'which', return_value=str(executable)),
                        patch.dict(os.environ, {'LQA_SSH_LOG': str(self.log)})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_batch_authenticates_once_sends_all_bytes_and_retires_socket(self):
        payload = bytes(range(256)) * 8192
        with ssh.ssh_connection('synthetic.invalid', port=2222) as connection:
            socket = connection.socket
            self.assertEqual(socket.parent.stat().st_mode & 0o777, 0o700)
            for body in (payload, b''):
                with ssh.ssh_stream('synthetic.invalid', 'digest', lambda: False, port=2222,
                                    connection=connection, input_data=body) as stream:
                    self.assertEqual(stream.read().decode(), sha256(body).hexdigest())
            calls = self.calls()
            self.assertEqual(sum('-N' in args for args in calls), 1)
            for args in calls[1:]:
                self.assertIn('BatchMode=yes', args)
                self.assertIn('ProxyCommand=false', args)
                self.assertIn('ForwardAgent=no', args)
                self.assertIn('ClearAllForwardings=yes', args)
                self.assertIn('ControlPath=' + str(socket), args)
        self.assertIsNotNone(connection.process.poll())
        self.assertFalse(socket.parent.exists())
        with self.assertRaises(OSError):
            connection.check('synthetic.invalid', 2222)

    def test_default_transport_keeps_noninteractive_and_host_trust_contract(self):
        with patch.dict(os.environ, {'SSH_ASKPASS': ''}), patch.object(ssh.sys, 'platform', 'linux'):
            with ssh.ssh_stream('synthetic.invalid', 'digest', lambda: False) as stream:
                self.assertEqual(stream.read().decode(), sha256(b'').hexdigest())
        args = self.calls()[0]
        self.assertIn('ControlPath=none', args)
        self.assertIn('StrictHostKeyChecking=yes', args)
        self.assertIn('BatchMode=yes', args)
        self.assertNotIn('ProxyCommand=false', args)

    def test_invalid_endpoint_or_stale_session_never_starts_client(self):
        for host, port in (('-option', 22), ('root@host', 22), ('host;command', 22), ('host', 0)):
            with self.subTest(host=host, port=port), self.assertRaises(ValueError):
                with ssh.ssh_connection(host, port=port):
                    self.fail('invalid endpoint accepted')
        self.assertFalse(self.log.exists())
        with ssh.ssh_connection('synthetic.invalid') as connection:
            with self.assertRaises(ValueError):
                with ssh.ssh_stream('other.invalid', 'digest', lambda: False, connection=connection):
                    self.fail('cross-endpoint session accepted')
            os.killpg(connection.process.pid, signal.SIGKILL)
            connection.process.wait()
            with self.assertRaises(OSError):
                with ssh.ssh_stream('synthetic.invalid', 'digest', lambda: False, connection=connection):
                    self.fail('dead session accepted')
        self.assertEqual(len(self.calls()), 1)

    def test_login_failure_timeout_and_cancellation_retire_master(self):
        for mode, exception in (('reject', OSError), ('wait', TimeoutError), ('cancel', OperationCancelled)):
            with self.subTest(mode=mode), patch.dict(os.environ, {'LQA_SSH_MODE': mode}):
                def cancelled():
                    return mode == 'cancel' and self.log.exists()
                self.log.unlink(missing_ok=True)
                with self.assertRaises(exception):
                    with ssh.ssh_connection('synthetic.invalid', cancelled, timeout=.2):
                        self.fail('login unexpectedly succeeded')
                args = self.calls()[0]
                socket = Path(next(arg.split('=', 1)[1] for arg in args if arg.startswith('ControlPath=')))
                self.assertFalse(socket.parent.exists())

    def test_cancelled_blocking_input_and_early_exit_do_not_report_success(self):
        with ssh.ssh_connection('synthetic.invalid') as connection:
            cancel = False
            with self.assertRaises(OperationCancelled):
                with ssh.ssh_stream('synthetic.invalid', 'wait', lambda: cancel,
                                    connection=connection, input_data=b'x' * (4 * 1024 * 1024)) as stream:
                    cancel = True
                    stream.read()
            with self.assertRaises(BrokenPipeError):
                with ssh.ssh_stream('synthetic.invalid', 'early', lambda: False,
                                    connection=connection, input_data=b'x' * (4 * 1024 * 1024)) as stream:
                    stream.read()
            connection.check('synthetic.invalid', 22)
