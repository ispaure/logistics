"""Credential preparation never publishes; stale/single-use admission erases staging."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from concurrent.futures import ThreadPoolExecutor
import gc
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

from commonUtils.runtime.operations import OperationCancelled
from features.rclone import session
from features.rclone.credential_loading import CredentialContext
from features.rclone.desktop_credentials import DesktopCredentialLoad, DesktopCredentials
from features.rclone.service import CredentialService


class CredentialServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.key = self.root / 'Account.session'
        self.request = DesktopCredentialLoad(self.root / 'Account.zip', self.key)
        self.service = CredentialService(DesktopCredentials())
        self.addCleanup(session.forget, self.key)

    def prepare(self, **kwargs):
        values = {'Files': {'type': 'local', 'token': 'private-token'}}
        with patch.object(session, 'read_package', return_value=values):
            prepared = self.service.prepare_load(self.request, 'private-password', **kwargs)
        return prepared, values

    def test_preparation_is_private_and_publication_copies_before_erasing_staging(self):
        prepared, values = self.prepare()
        self.assertIsNone(session.credentials(self.key))
        self.assertNotIn('private-', repr(prepared))
        result = self.service.unlock(prepared)
        self.assertEqual(result.remotes, ('Files',))
        self.assertFalse(result.saved)
        self.assertEqual(values, {})
        self.assertEqual(session.credentials(self.key)['Files']['token'], 'private-token')
        with self.assertRaises(ValueError):
            self.service.unlock(prepared)

    def test_discard_foreign_service_and_gc_do_not_publish(self):
        prepared, values = self.prepare()
        with self.assertRaises(ValueError):
            CredentialService(DesktopCredentials()).unlock(prepared)
        self.service.discard(prepared)
        self.assertEqual(values, {})
        with self.assertRaises(ValueError):
            self.service.unlock(prepared)
        prepared, values = self.prepare()
        del prepared
        gc.collect()
        self.assertEqual(values, {})
        self.assertIsNone(session.credentials(self.key))

    def test_lock_erases_pending_settings_and_prevents_reopening(self):
        prepared, values = self.prepare()
        self.service.lock(self.key)
        self.assertEqual(values, {})
        with self.assertRaises(ValueError):
            self.service.unlock(prepared)
        self.assertIsNone(session.credentials(self.key))

    def test_forget_removes_both_saved_file_and_loaded_session_and_keeps_zip(self):
        config = self.root / 'Account.conf'
        package = self.root / 'Account.zip'
        package.write_bytes(b'original encrypted ZIP')
        config.write_text('[Files]\ntype = local\n')
        session.remember(config, {'Files': {'type': 'local'}}, package_path=package)
        grant = self.service.capture(config)
        prepared, values = self.prepare()
        self.assertEqual(self.service.forget(config), [config])
        self.assertFalse(config.exists())
        self.assertIsNone(session.credentials(config))
        self.assertIsNone(session.package_path(config))
        self.assertEqual(package.read_bytes(), b'original encrypted ZIP')
        self.assertEqual(values, {})
        with self.assertRaises(ValueError):
            grant.check()
        with self.assertRaises(ValueError):
            self.service.unlock(prepared)

    def test_forget_still_deletes_saved_file_when_revocation_callback_fails(self):
        config = self.root / 'Account.conf'
        config.write_text('[Files]\ntype = local\n')
        with patch.object(self.service._backend, 'lock', side_effect=OSError('Observer failed')):
            with self.assertRaises(OSError):
                self.service.forget(config)
        self.assertFalse(config.exists())

    def test_forget_all_saved_configs_keeps_session_only_credentials(self):
        from features.rclone import configuration
        config = self.root / 'Account.conf'
        config.write_text('[Files]\ntype = local\n')
        session.remember(self.key, {'Files': {'type': 'local'}})
        with patch.object(configuration, 'get_rclone_config_dir', return_value=self.root):
            self.assertEqual(self.service.forget(), [config])
        self.assertEqual(session.names(self.key), ['Files'])

    def test_lock_retains_zip_shortcut_but_explicit_forget_erases_it(self):
        from features.rclone import desktop_catalog
        package = self.root / 'Account.zip'
        session.remember(self.key, {'Files': {'type': 'local'}}, package_path=package)
        desktop_catalog.remember(self.key, package, ['Files'])
        self.service.lock(self.key)
        self.assertEqual(session.package_path(self.key), package)
        self.service.forget(self.key)
        self.assertIsNone(session.package_path(self.key))
        self.assertIsNone(desktop_catalog.read(self.key))

    def test_forget_rejects_original_zip(self):
        package = self.root / 'Account.zip'
        package.write_bytes(b'original')
        with self.assertRaises(ValueError):
            self.service.forget(package)
        self.assertEqual(package.read_bytes(), b'original')

    def test_saved_grants_follow_lock_all_and_file_replacement_across_services(self):
        config = self.root / 'Account.CONF'
        config.write_text('[Files]\ntype = local\n')
        grant = self.service.capture(config)
        other = CredentialService(DesktopCredentials())
        other.lock(config)
        with self.assertRaises(ValueError):
            grant.check()
        reopened = self.service.capture(config)
        reopened.check()
        other.lock()
        with self.assertRaises(ValueError):
            reopened.check()
        replacement = self.service.capture(config)
        config.write_text('[Different]\ntype = local\n')
        with self.assertRaises(ValueError):
            replacement.check()

    def test_lock_during_slow_decode_prevents_late_publication(self):
        started, release = Event(), Event()
        values = {'Files': {'type': 'local'}}
        def decode(*args):
            started.set()
            if not release.wait(5):
                raise TimeoutError('Fixture was not released')
            return values
        with patch.object(session, 'read_package', side_effect=decode), ThreadPoolExecutor() as workers:
            loading = workers.submit(self.service.prepare_load, self.request, 'password')
            try:
                self.assertTrue(started.wait(2))
                self.service.lock(self.key)
            finally:
                release.set()
            with self.assertRaises(ValueError):
                loading.result(2)
        self.assertEqual(values, {})
        self.assertIsNone(session.credentials(self.key))

    def test_new_publication_erases_other_pending_loads(self):
        first, first_values = self.prepare()
        second, second_values = self.prepare()
        self.service.unlock(first)
        self.assertEqual(first_values, {})
        self.assertEqual(second_values, {})
        with self.assertRaises(ValueError):
            self.service.unlock(second)

    def test_replaced_generation_and_retired_host_refuse_publication(self):
        for changed in ('generation', 'host'):
            with self.subTest(changed=changed):
                session.remember(self.key, {'Old': {'type': 'local'}})
                active = [True]
                prepared, values = self.prepare(context=CredentialContext(valid=lambda: active[0]))
                if changed == 'generation':
                    session.remember(self.key, {'Old': {'type': 'local'}})
                else:
                    active[0] = False
                with self.assertRaises(ValueError):
                    self.service.unlock(prepared)
                self.assertEqual(values, {})
                self.assertEqual(list(session.credentials(self.key)), ['Old'])

    def test_inflight_publication_refuses_other_loads_without_waiting(self):
        from features.rclone.credential_loading import CredentialBusyError
        started, release = Event(), Event()
        prepared, _ = self.prepare()
        remember = session.remember
        def paused(*args, **kwargs):
            started.set()
            if not release.wait(5):
                raise TimeoutError('Fixture was not released')
            return remember(*args, **kwargs)
        with patch.object(session, 'remember', side_effect=paused), ThreadPoolExecutor() as workers:
            publishing = workers.submit(self.service.unlock, prepared)
            try:
                self.assertTrue(started.wait(2))
                with self.assertRaises(CredentialBusyError):
                    self.prepare()
            finally:
                release.set()
            self.assertEqual(publishing.result(2).remotes, ('Files',))

    def test_invalid_crypt_settings_do_not_replace_existing_access(self):
        session.remember(self.key, {'Old': {'type': 'local'}})
        values = {'Secret': {'type': 'crypt', 'remote': 'Backing:'}, 'Backing': {'type': 'local'}}
        request = DesktopCredentialLoad(self.request.package, self.key, crypt_remote='Secret')
        with patch.object(session, 'read_package', return_value=values):
            with self.assertRaises(ValueError):
                self.service.load(request, 'password')
        self.assertEqual(list(session.credentials(self.key)), ['Old'])
        self.assertEqual(values, {})

    def test_saved_write_cancellation_at_publication_preserves_original_file(self):
        from commonUtils.persistence import atomic_write_bytes
        path = self.root / 'Account.conf'
        original = b'[Old]\ntype = local\n'
        path.write_bytes(original)
        cancelled = Event()
        def interrupted(target, data, **kwargs):
            cancelled.set()
            return atomic_write_bytes(target, data, **kwargs)
        with patch.object(session, 'read_package', return_value={'New': {'type': 'local'}}), patch(
                'commonUtils.persistence.atomic_write_bytes', side_effect=interrupted):
            with self.assertRaises(OperationCancelled):
                self.service.load(DesktopCredentialLoad(self.request.package, path, True), 'password',
                                  CredentialContext(cancelled.is_set))
        self.assertEqual(path.read_bytes(), original)

    def test_invalid_package_preserves_both_active_access_and_saved_config(self):
        path = self.root / 'Account.conf'
        path.write_bytes(b'original saved config')
        session.remember(self.key, {'Old': {'type': 'local'}})
        grant = self.service.capture(self.key)
        with patch.object(session, 'read_package', side_effect=ValueError('Bad password')):
            with self.assertRaises(ValueError):
                self.service.load(DesktopCredentialLoad(self.request.package, path, True), 'wrong')
        grant.check()
        self.assertEqual(path.read_bytes(), b'original saved config')
