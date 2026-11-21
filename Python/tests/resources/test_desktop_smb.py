"""Desktop SMB admission, private storage and credential revocation."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.integrations.wrappers.cmdShellWrapper.binary import BinaryCommandError
from commonUtils.runtime.operations import OperationCancelled
from features.rclone import desktop_smb as smb, session
from features.rclone.credential_loading import CredentialContext
from features.rclone.desktop_credentials import DesktopCredentials
from features.rclone.remote_resources import remote_failure
from features.rclone.service import CredentialService


class DesktopSMBTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.object(smb, 'application_root', return_value=self.root))
        self.provider = self.enterContext(patch('features.rclone.remote_resources.RemoteResources'))
        self.run = self.enterContext(patch.object(smb, 'run_bytes', return_value=b'officially-obscured-test-password\n'))
        self.credentials = CredentialService(DesktopCredentials())
        self.record = smb.ServerRecord.new('Fixture')
        self.endpoint = smb.SMBEndpoint('127.0.0.1', 'test account', port='1445')
        self.addCleanup(session.forget, self.record.context)

    def request(self, *, adding=True, saved=False, record=None, cancelled=lambda: False):
        record = record or self.record
        return smb.DesktopSMBLoad(record, Path('rclone'), None if record.encrypted else self.endpoint,
                                  saved, adding, cancelled)

    def test_rejected_signin_leaves_profile_and_session_empty(self):
        self.provider.return_value.list.side_effect = OSError('The SMB server declined sign-in.')
        with self.assertRaisesRegex(OSError, 'declined'):
            self.credentials.load(self.request(), smb.SMBSecrets('generated test password'))
        self.assertEqual(smb.records(), [])
        self.assertIsNone(session.names(self.record.context))
        self.provider.return_value.close.assert_called_once()
        temporary_context = self.provider.call_args.args[0]
        self.assertIsNone(session.credentials(temporary_context))

    def test_session_only_persists_label_and_reconnect_requires_new_credentials(self):
        result = self.credentials.load(self.request(), smb.SMBSecrets('generated test password'))
        self.assertFalse(result.saved)
        self.assertEqual(json.loads(self.record.path.read_text()),
                         {'schema': 1, 'name': 'Fixture', 'encrypted': ''})
        argv, = self.run.call_args.args
        self.assertNotIn('generated test password', argv)
        self.assertEqual(self.run.call_args.kwargs['input_data'], b'generated test password\n')
        grant = self.credentials.capture(result.key)
        self.credentials.lock()
        with self.assertRaisesRegex(ValueError, 'locked'):
            grant.check()
        self.assertFalse(smb.records()[0].connected)
        self.credentials.load(self.request(adding=False), smb.SMBSecrets('new test password'))
        self.assertTrue(smb.records()[0].connected)
        with self.assertRaisesRegex(ValueError, 'locked'):
            grant.check()

    def test_saved_credentials_are_encrypted_and_forgotten_with_the_record(self):
        secret = smb.SMBSecrets('generated test password', 'generated test passphrase')
        result = self.credentials.load(self.request(saved=True), secret)
        self.assertTrue(result.saved)
        stored = smb.records()[0]
        self.assertTrue(stored.encrypted)
        self.assertNotIn(b'generated test password', stored.path.read_bytes())
        self.assertNotIn(b'127.0.0.1', stored.path.read_bytes())
        self.credentials.lock(result.key)
        request = self.request(adding=False, record=stored)
        with self.assertRaisesRegex(ValueError, 'Check the passphrase'):
            self.credentials.load(request, smb.SMBSecrets(passphrase='invalid passphrase'))
        self.assertFalse(stored.connected)
        self.credentials.load(request, smb.SMBSecrets(passphrase=secret.passphrase))
        self.assertTrue(stored.connected)
        smb.forget(stored)
        self.assertFalse(stored.connected)
        self.assertEqual(smb.records(), [])

    def test_cancel_or_lock_between_probe_and_commit_does_not_publish(self):
        for lock in (False, True):
            with self.subTest(lock=lock):
                cancelled = False
                stopping = lambda: cancelled
                request = self.request(cancelled=stopping)
                prepared = self.credentials.prepare_load(request, smb.SMBSecrets(), CredentialContext(stopping))
                if lock:
                    self.credentials.lock()
                else:
                    cancelled = True
                with self.assertRaises((ValueError, OperationCancelled)):
                    self.credentials.unlock(prepared)
                self.assertEqual(smb.records(), [])
                self.assertFalse(self.record.connected)

    def test_endpoint_validates_hostname_and_normalizes_ipv6(self):
        for address in ('smb://host', 'host/share', 'host:445', 'name\nwith control'):
            with self.subTest(address=address), self.assertRaisesRegex(ValueError, 'hostname'):
                smb.SMBEndpoint(address, 'guest').settings()
        self.assertEqual(smb.SMBEndpoint('::1', 'guest').settings()['host'], '[::1]')
        self.assertEqual(smb.SMBEndpoint('[::1]', 'guest').settings()['host'], '[::1]')

    def test_smb_errors_are_actionable_and_hide_raw_details(self):
        for diagnostic, expected in (
            ('dial tcp: connection refused', 'Could not reach'),
            ('The attempted logon is invalid.', 'declined sign-in'),
            ('{Network Name Not Found}', 'share or folder was not found'),
            ('{Access Denied}', 'denied access'),
        ):
            with self.subTest(diagnostic=diagnostic):
                error = BinaryCommandError(1, (diagnostic + ' private-fixture-detail').encode())
                message = remote_failure(error, smb=True)
                self.assertIn(expected, message)
                self.assertNotIn('private-fixture-detail', message)
