"""Retention uses identity metadata; forgetting attempts independent erasures."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from threading import RLock
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import Mock

from features.rclone.mobile.credential_retention import NativeCredentialRetention, NativeCredentialForget
from features.rclone.mobile.credential_packages import CredentialPackages
from features.rclone.mobile.service import native_service
from features.rclone.mobile.cloud import CloudClient
from features.rclone.mobile.credential_loading import NativeCredentialLoad
from features.rclone.credential_loading import CredentialBusyError
from test_native_credential_service import Client, Package


class RetentionTests(unittest.TestCase):
    def test_package_metadata_failure_does_not_skip_its_known_document_list_erasure(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / ('a' * 64)
            cache.mkdir()
            (cache / ('b' * 64 + '.zip')).write_bytes(b'encrypted list fixture')
            client = Client()
            client.package_records = (dict(package_name='Fixture.zip', document_cache_id='a' * 64),)
            client.forget_package = Mock()
            packages = Mock(side_effect=OSError('Package index unavailable'))
            with self.assertRaisesRegex(OSError, 'Package index unavailable'):
                native_service(client).credentials.forget(NativeCredentialForget(packages, root, 'Fixture.zip'))
            client.forget_package.assert_called_once_with('Fixture.zip')
            self.assertFalse(cache.exists())

    def test_package_forget_vault_failure_still_revokes_live_access_and_erases_caches(self):
        with TemporaryDirectory() as directory:
            client = Client()
            client.package_records = (dict(package_name='Fixture.zip', document_cache_id='a' * 64),)
            client.forget_package = Mock(side_effect=OSError('Saved vault key unavailable'))
            store = SimpleNamespace(client=client, forget_package=Mock())
            root = Path(directory)
            cache = root / ('a' * 64)
            cache.mkdir()
            (cache / ('b' * 64 + '.zip')).write_bytes(b'encrypted cache')
            service = native_service(client).credentials
            grant = service.capture('Fixture.zip')
            with self.assertRaisesRegex(OSError, 'Saved vault key unavailable'):
                service.forget(NativeCredentialForget(lambda: store, root, 'Fixture.zip'))
            with self.assertRaises(ValueError):
                grant.check()
            store.forget_package.assert_called_once_with('Fixture.zip')
            self.assertFalse(cache.exists())

    def test_retain_resolves_alias_identity_and_rejects_stale_or_foreign_store(self):
        client = Client()
        client.connection_identity = Mock(return_value='a' * 64)
        client.package_records = ({'package_name': 'Fixture.zip', 'aliases': {'Original': 'Alias', 'Other': 'Elsewhere'}},)
        store = SimpleNamespace(client=client, remember=Mock(return_value='retained-key'))
        package = SimpleNamespace(name='Fixture.zip', data=b'original')
        service = native_service(client).credentials
        request = NativeCredentialRetention(store, package, ('Alias',), client.generation, ('Alias',))
        grant = service.capture('Fixture.zip')
        self.assertEqual(service.retain(request), 'retained-key')
        store.remember.assert_called_once_with(package, {'Alias': 'a' * 64},
            aliases={'Original': 'Alias'}, crypt_remotes=('Alias',))
        grant.check()
        client.generation += 1
        with self.assertRaises(ValueError):
            service.retain(request)
        store.client = Client()
        with self.assertRaises(ValueError):
            service.retain(request)
        self.assertEqual(store.remember.call_count, 1)

    def test_forgetting_failure_still_retires_load_and_other_stores(self):
        with TemporaryDirectory() as directory:
            client = Client()
            def clear():
                client.lock()
                raise OSError('Saved vault key deletion failed')
            client.clear = clear
            store = SimpleNamespace(client=client, forget=Mock())
            root = Path(directory)
            entry = root / ('b' * 64)
            entry.mkdir()
            (entry / ('c' * 64 + '.zip')).write_bytes(b'encrypted')
            service = native_service(client).credentials
            pending = service.prepare_load(NativeCredentialLoad(Package(), None), 'correct')
            with self.assertRaises(OSError):
                service.forget(NativeCredentialForget(lambda: store, root))
            store.forget.assert_called_once()
            self.assertEqual(list(root.iterdir()), [])
            with self.assertRaises(ValueError):
                service.unlock(pending)

    def test_forget_handles_corrupt_index_and_orphaned_package_blob(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            index = root / 'packages.json'
            index.write_text('broken json')
            blob = root / ('a' * 64 + '.bin')
            blob.write_bytes(b'orphaned encrypted ZIP')
            vault = SimpleNamespace(root=root, forget=Mock(side_effect=OSError('Key store unavailable')))
            store = CredentialPackages(vault, Client(), load=False)
            with self.assertRaises(OSError):
                store.forget()
            self.assertFalse(blob.exists())
            self.assertTrue(index.exists())
            vault.forget.side_effect = None
            store.forget()
            self.assertFalse(index.exists())
            self.assertEqual(list(root.iterdir()), [])

    def test_clear_attempts_vault_erasure_even_when_native_lock_observer_fails(self):
        client = object.__new__(CloudClient)
        from features.rclone.mobile.credential_state import NativeCredentialState
        client.credential_state = NativeCredentialState()
        class Observer:
            def credentials_changed(self):
                raise OSError('Observer failed after revocation')
        observer = Observer()
        client.credential_state.observers.add(observer)
        def clear(action):
            client.credential_state.publish(action, {}, {})
        client._request = clear
        client.vault = SimpleNamespace(forget=Mock())
        with self.assertRaisesRegex(OSError, 'Observer failed after revocation'):
            client.clear()
        client.vault.forget.assert_called_once()

    def test_retention_refuses_another_scenes_active_publication(self):
        client = Client()
        client.credential_state = SimpleNamespace(lock=RLock())
        service = native_service(client).credentials
        with client.credential_state.lock, ThreadPoolExecutor() as workers:
            retained = workers.submit(service.retain, object())
            with self.assertRaises(CredentialBusyError):
                retained.result(2)

    def test_retained_metadata_changes_and_forgetting_reach_other_scenes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            client = Client()
            client.request = lambda action, **values: values['data']
            vault = SimpleNamespace(root=root, unlock=lambda **kwargs: {'key': 'fixture'}, forget=Mock())
            first = CredentialPackages(vault, client)
            second = CredentialPackages(vault, client)
            data = (Path(__file__).resolve().parents[2] / 'rclone_bridge/testdata/credentials-aes256.zip').read_bytes()
            package = SimpleNamespace(name='Fixture.zip', data=data)
            key = first.remember(package, {'Alias': 'a' * 64})
            self.assertIn(key, second.items)
            first.update_crypt_remotes(key, ['Alias'])
            self.assertEqual(second.items[key]['crypt_remotes'], ['Alias'])
            second.forget()
            self.assertEqual(first.items, {})
            self.assertFalse(first.path(key).exists())

    def test_failed_emergency_lock_reports_uncertain_access_and_attempts_remaining_cleanup(self):
        with TemporaryDirectory() as directory:
            client = Client()
            client.forget_package = Mock(side_effect=OSError('Vault unavailable'))
            client.lock = Mock(side_effect=OSError('Bridge unavailable'))
            store = SimpleNamespace(client=client, forget_package=Mock())
            with self.assertRaisesRegex(OSError, 'session locking could not be confirmed'):
                native_service(client).credentials.forget(
                    NativeCredentialForget(lambda: store, Path(directory), 'Fixture.zip'))
            store.forget_package.assert_called_once_with('Fixture.zip')
