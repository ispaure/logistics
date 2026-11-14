"""Run the publication/recovery shell against synthetic files and services."""
from dataclasses import replace
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.testing.stages import TestStage
from features.notebooks.remarkable_mutations import MetadataRevision, plan_metadata_change
from features.notebooks import remarkable_transaction as transactions

TEST_STAGE = TestStage.REGRESSION
DOC = '11111111-1111-4111-8111-111111111111'
FOLDER = '22222222-2222-4222-8222-222222222222'

UTILITIES = r'''
import hashlib, os, pathlib, signal, stat, subprocess, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
state = pathlib.Path(os.environ['LQA_SERVICE_STATE'])
if name == 'systemctl':
    if args[0] == 'is-active':
        print(state.read_text() if args[1] in ('xochitl', 'rm-sync') else 'inactive')
    elif args[0] == 'stop':
        state.write_text('inactive')
    elif args[0] == 'start':
        if os.environ.get('LQA_FAIL_RESTART'):
            sys.exit(1)
        state.write_text('active')
    elif args[0] == 'show':
        print('ActiveState=inactive\nSubState=dead\nResult=success')
    else:
        sys.exit('Unexpected service command')
elif name == 'systemd-run':
    # Simulate systemd's unconditional ExecStopPost; native qualification must
    # separately establish actual detachment, timeout and restart behavior.
    entry = args[args.index('/bin/sh') + 1]
    result = subprocess.run(['/bin/sh', entry])
    post = next((arg.split('=', 2)[2] for arg in args if arg.startswith('--property=ExecStopPost=')), None)
    if post:
        subprocess.run(['/bin/sh', post.removeprefix('/bin/sh ')], check=True)
    sys.exit(result.returncode)
elif name == 'sha256sum':
    if os.environ.get('LQA_FAIL_HASH') and args[0] == os.environ['LQA_TARGET']:
        sys.exit(1)
    print(hashlib.sha256(pathlib.Path(args[0]).read_bytes()).hexdigest(), args[0])
elif name == 'stat':
    info = pathlib.Path(args[2]).stat()
    print({'%u': '0', '%a': oct(stat.S_IMODE(info.st_mode))[2:], '%d': str(info.st_dev)}[args[1]])
elif name == 'sync':
    pass
elif name == 'timeout':
    sys.exit(subprocess.run(args[1:]).returncode)
elif name == 'head':
    # This firmware's BusyBox head does not include byte-count support.
    if '-c' in args:
        sys.exit(2)
    sys.exit(subprocess.run(['/usr/bin/head', *args]).returncode)
elif name == 'mv':
    publication = args[-1] == os.environ['LQA_TARGET']
    point = os.environ.get('LQA_KILL_AT') if publication else ''
    if point == 'before':
        os.kill(os.getppid(), signal.SIGKILL)
        sys.exit(0)
    subprocess.run(['/bin/mv', *args], check=True)
    if point == 'after':
        os.kill(os.getppid(), signal.SIGKILL)
'''


@unittest.skipUnless(os.name == 'posix', 'The firmware transaction scripts require a POSIX shell.')
class MetadataTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.store = self.root / 'store'
        self.store.mkdir()
        self.transactions = self.root / 'transactions'
        self.transactions.mkdir(mode=0o700)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        for name in ('systemctl', 'systemd-run', 'sha256sum', 'stat', 'sync', 'timeout', 'mv', 'head'):
            executable = self.bin / name
            executable.write_text('#!' + sys.executable + '\n' + UTILITIES)
            executable.chmod(0o700)
        self.services = self.root / 'services'
        self.services.write_text('active')
        self.before = json.dumps(dict(type='DocumentType', visibleName='Original', parent='', lastModified='1000')).encode()
        folder = json.dumps(dict(type='CollectionType', visibleName='Folder', parent='', lastModified='1000')).encode()
        self.records = {DOC: self.before, FOLDER: folder}
        for identity, data in self.records.items():
            (self.store / (identity + '.metadata')).write_bytes(data)
        self.target = self.store / (DOC + '.metadata')
        self.target.chmod(0o640)
        (self.store / (DOC + '.content')).write_bytes(b'preserve opaque content')
        (self.store / 'unselected.metadata').write_bytes(b'private sentinel')
        self.change = plan_metadata_change(self.records, DOC, 'move', destination=FOLDER, modified_ms=1001)
        for patcher in (patch.object(transactions, 'STORE_PATH', str(self.store)),
                        patch.object(transactions, 'TRANSACTION_ROOT', str(self.transactions))):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.transaction = transactions.prepare_metadata_transaction(self.change)
        self.stage = Path(self.transaction.directory)
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                        LQA_SERVICE_STATE=str(self.services), LQA_TARGET=str(self.target), COPYFILE_DISABLE='1')

    def run_command(self, command, *, payload=None, **environment):
        return subprocess.run(['/bin/sh', '-c', command], cwd=self.store, env=dict(self.env, **environment),
                              input=payload, capture_output=True, timeout=10)

    def prepare(self):
        self.stage.mkdir(mode=0o700)
        with tarfile.open(fileobj=BytesIO(self.transaction.archive)) as archive:
            for member in archive:
                self.assertTrue(member.isfile())
                self.assertNotIn('/', member.name)
                (self.stage / member.name).write_bytes(archive.extractfile(member).read())

    def run_script(self, name, **environment):
        return self.run_command('/bin/sh ' + str(self.stage / name), **environment)

    def assert_preserved(self):
        self.assertEqual((self.store / (DOC + '.content')).read_bytes(), b'preserve opaque content')
        self.assertEqual((self.store / 'unselected.metadata').read_bytes(), b'private sentinel')
        self.assertEqual((self.store / (FOLDER + '.metadata')).read_bytes(), self.records[FOLDER])

    def test_complete_publication_restart_and_owned_cleanup(self):
        result = self.run_command(self.transaction.launch_command, payload=self.transaction.archive)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.target.read_bytes(), self.change.after)
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o640)
        self.assertEqual((self.stage / 'original').read_bytes(), self.before)
        self.assertEqual((self.stage / 'outcome').read_text().strip(), 'committed')
        self.assertEqual(self.services.read_text(), 'active')
        self.assertFalse((self.transactions / 'active').exists())
        self.assert_preserved()
        result = self.run_command(self.transaction.inspect_command)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'outcome=committed', result.stdout)
        (self.stage / 'outcome').write_text('unexpected receipt\n')
        self.assertNotEqual(self.run_command(self.transaction.inspect_command).returncode, 0)
        (self.stage / 'outcome').write_text('committed\n')
        result = self.run_command(self.transaction.cleanup_command)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.stage.exists())

    def test_killed_publication_recovers_old_or_new_record_without_guessing(self):
        for point, outcome in (('before', 'unchanged'), ('after', 'committed')):
            with self.subTest(point=point):
                self.transaction = transactions.prepare_metadata_transaction(self.change)
                self.stage = Path(self.transaction.directory)
                self.target.write_bytes(self.before)
                self.prepare()
                result = self.run_script('apply.sh', LQA_KILL_AT=point)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.services.read_text(), 'inactive')
                self.assertEqual(self.run_script('restart.sh').returncode, 0)
                self.assertEqual((self.stage / 'outcome').read_text().strip(), outcome)
                self.assertEqual(self.target.read_bytes(), self.before if point == 'before' else self.change.after)
                self.assertEqual(self.services.read_text(), 'active')
                self.assert_preserved()

    def test_failed_restart_keeps_lease_until_explicit_recovery(self):
        self.prepare()
        self.assertEqual(self.run_script('apply.sh').returncode, 0)
        self.assertNotEqual(self.run_script('restart.sh', LQA_FAIL_RESTART='yes').returncode, 0)
        self.assertTrue((self.transactions / 'active').exists())
        self.assertFalse((self.stage / 'service-state').exists())
        self.assertNotEqual(self.run_command(self.transaction.cleanup_command).returncode, 0)
        self.assertEqual(self.run_command(self.transaction.recovery_command).returncode, 0)
        self.assertEqual(self.services.read_text(), 'active')
        self.assertFalse((self.transactions / 'active').exists())

    def test_receipt_failure_cannot_prevent_interface_restart(self):
        self.prepare()
        self.assertEqual(self.run_script('apply.sh').returncode, 0)
        (self.stage / 'outcome.tmp').mkdir()
        self.assertNotEqual(self.run_script('restart.sh', LQA_FAIL_HASH='yes').returncode, 0)
        self.assertEqual(self.services.read_text(), 'active')
        self.assertTrue((self.transactions / 'active').exists())
        self.assertEqual(self.target.read_bytes(), self.change.after)
        (self.stage / 'outcome.tmp').rmdir()
        self.assertEqual(self.run_script('restart.sh', LQA_FAIL_HASH='yes').returncode, 0)
        self.assertEqual((self.stage / 'outcome').read_text().strip(), 'conflict')
        self.assertEqual(self.services.read_text(), 'active')

    def test_stale_ancestor_or_symlink_blocks_publication_and_restarts(self):
        self.prepare()
        ancestor = self.store / (FOLDER + '.metadata')
        ancestor.write_bytes(self.records[FOLDER] + b' ')
        self.assertNotEqual(self.run_script('apply.sh').returncode, 0)
        self.assertEqual(self.run_script('restart.sh').returncode, 0)
        self.assertEqual(self.target.read_bytes(), self.before)
        self.assertEqual(self.services.read_text(), 'active')
        ancestor.unlink()
        ancestor.symlink_to(self.target)
        self.assertNotEqual(self.run_script('apply.sh').returncode, 0)
        self.assertEqual(self.run_script('restart.sh').returncode, 0)
        self.assertEqual(self.target.read_bytes(), self.before)

    def test_foreign_edit_or_recovery_member_is_preserved_and_blocks_cleanup(self):
        self.prepare()
        self.assertNotEqual(self.run_script('apply.sh', LQA_KILL_AT='before').returncode, 0)
        self.target.write_bytes(b'foreign concurrent edit')
        self.assertEqual(self.run_script('restart.sh').returncode, 0)
        self.assertEqual((self.stage / 'outcome').read_text().strip(), 'conflict')
        self.assertNotEqual(self.run_command(self.transaction.cleanup_command).returncode, 0)
        self.assertEqual(self.target.read_bytes(), b'foreign concurrent edit')
        (self.stage / 'outcome').write_text('unchanged\n')
        (self.stage / '.unexpected').write_bytes(b'preserve')
        before = {item.name: item.read_bytes() for item in self.stage.iterdir()}
        self.assertNotEqual(self.run_command(self.transaction.cleanup_command).returncode, 0)
        self.assertEqual({item.name: item.read_bytes() for item in self.stage.iterdir()}, before)

    def test_other_lease_and_repeated_or_incomplete_upload_never_replace_state(self):
        self.prepare()
        lease = self.transactions / 'active'
        lease.write_text('another transaction')
        self.assertNotEqual(self.run_script('apply.sh').returncode, 0)
        self.assertEqual(self.run_script('restart.sh').returncode, 0)
        self.assertEqual(lease.read_text(), 'another transaction')
        self.assertEqual(self.services.read_text(), 'active')
        self.assertEqual(self.target.read_bytes(), self.before)
        result = self.run_command(self.transaction.launch_command, payload=self.transaction.archive)
        self.assertNotEqual(result.returncode, 0)
        partial = transactions.prepare_metadata_transaction(self.change)
        result = self.run_command(partial.launch_command, payload=partial.archive[:123])
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((Path(partial.directory) / 'apply.sh').exists())
        self.assertEqual(self.target.read_bytes(), self.before)

    def test_malformed_change_never_becomes_shell_source(self):
        for change in (replace(self.change, identity='../escape'),
                       replace(self.change, guards=(MetadataRevision(DOC, '$(command)'),)),
                       replace(self.change, before=b'different'),
                       replace(self.change, after=self.change.before)):
            with self.subTest(change=change), self.assertRaises(ValueError):
                transactions.prepare_metadata_transaction(change)
