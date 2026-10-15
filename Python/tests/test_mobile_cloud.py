"""Private-copy and scoped credential boundaries; native engine has its own gates."""
import base64
import ctypes
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

from commonUtils.runtime.document_access import LocalDocuments
from features.rclone.mobile.cloud import CloudClient, Downloads, download_name, PACKAGE_LIMIT


def seed_download(store, name, data):
    """Represent a completed private copy created by an older app version."""
    from uuid import uuid4
    folder = store.root / uuid4().hex
    folder.mkdir()
    target = folder / name
    target.write_bytes(data)
    (folder / '.complete').write_text(name)
    return target


class MobileCloudTests(unittest.TestCase):
    def test_privacy_gate_tracks_only_successful_session_loads_across_clients(self):
        previous = CloudClient._session_privacy
        self.addCleanup(setattr, CloudClient, '_package_privacy', CloudClient._package_privacy)
        CloudClient._package_privacy = {}
        self.addCleanup(setattr, CloudClient, '_session_privacy', previous)
        buffers = []
        response = {'ok': True, 'result': []}
        def call(action, data):
            buffer = ctypes.create_string_buffer(json.dumps(response).encode())
            buffers.append(buffer)
            return ctypes.addressof(buffer)
        first, second = CloudClient.__new__(CloudClient), CloudClient.__new__(CloudClient)
        first.call, first.free = call, lambda pointer: None
        first.request('import', session_only=True, password='session-password')
        gate = first.session_privacy
        self.assertIs(second.session_privacy, gate)
        self.assertTrue(gate.verify('session-password'))
        self.assertFalse(gate.verify('wrong'))
        response.update(ok=False, error='Wrong ZIP password')
        with self.assertRaises(ValueError):
            first.request('import', session_only=True, password='wrong')
        self.assertIs(second.session_privacy, gate)
        response.update(ok=True)
        first.request('vault_open')
        self.assertIs(second.session_privacy, gate)
        first.request('add_smb', session_only=True, password='smb-password')
        self.assertTrue(second.session_privacy.verify('smb-password'))
        first.request('clear')
        self.assertIsNone(second.session_privacy)
        first.request('import', session_only=False, password='saved-password')
        self.assertIsNone(second.session_privacy)

    def test_retired_mirror_operations_never_reach_native_bridge(self):
        client = CloudClient.__new__(CloudClient)
        client.call = Mock()
        for action in ('mirror_list', 'mirror_read', 'mirror_stat', 'mirror_mkdir', 'mirror_write', 'read', 'crypt_read', 'crypt_fetch'):
            with self.assertRaisesRegex(ValueError, 'Unsupported remote operation'):
                client.request(action)
        client.call.assert_not_called()

    def test_lock_unloads_credentials_without_forgetting_saved_vault(self):
        client = CloudClient.__new__(CloudClient)
        client.vault = SimpleNamespace(forget=Mock())
        client.request = Mock()
        client.package_name, client.vault_attached = 'Personal.zip', True
        client.lock()
        client.request.assert_called_once_with('clear')
        client.vault.forget.assert_not_called()
        self.assertEqual(client.package_name, '')
        self.assertFalse(client.vault_attached)
        client.clear()
        client.vault.forget.assert_called_once_with()

    def test_native_credential_replacement_invalidates_every_client(self):
        buffers = []
        def call(action, data):
            buffer = ctypes.create_string_buffer(b'{"ok":true,"result":[]}')
            buffers.append(buffer)
            return ctypes.addressof(buffer)
        first, second = CloudClient.__new__(CloudClient), CloudClient.__new__(CloudClient)
        first.call, first.free = call, lambda pointer: None
        second.vault_attached = True
        self.assertTrue(second.vault_attached)
        generation = second.generation
        first.request('clear')
        self.assertGreater(second.generation, generation)
        self.assertEqual(first.generation, second.generation)
        self.assertFalse(second.vault_attached)

    def test_mobile_cloud_downloads_recover_only_complete_private_copies(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            store = Downloads(root / 'Downloads')
            with patch('os.link', side_effect=PermissionError('No hard links')):
                first = seed_download(store, 'fixture.txt', b'private copy')
                second = seed_download(store, 'fixture.txt', b'another copy')
            self.assertNotEqual(first, second)
            self.assertEqual(len(Downloads(store.root).items()), 2)
            (first.parent / '.complete').unlink()
            self.assertEqual(store.items(), [second])
            first.unlink()
            first.symlink_to(second)
            (first.parent / '.complete').write_text(first.name)
            self.assertEqual(store.items(), [second])
            with self.assertRaises(ValueError):
                download_name('.complete')
            with self.assertRaises(ValueError):
                download_name('back\\slash.txt')

    def test_mobile_cloud_package_uses_scoped_read_without_saving_credentials(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / 'fixture.zip'
            source.write_bytes(b'synthetic encrypted ZIP bytes')
            client = CloudClient.__new__(CloudClient)
            requests = []
            client.request = lambda action, **values: requests.append((action, values)) or ['Fixture']
            self.assertEqual(client.import_package(LocalDocuments(), source, 'session-password'), ['Fixture'])
            self.assertEqual(base64.b64decode(requests[0][1]['package']), source.read_bytes())
            self.assertEqual(list(root.iterdir()), [source])
            source.write_bytes(b'x' * (PACKAGE_LIMIT + 1))
            with self.assertRaises(ValueError):
                client.import_package(LocalDocuments(), source, 'session-password')
            self.assertEqual(len(requests), 1)

    def test_mobile_cloud_bridge_frees_success_and_invalid_responses(self):
        buffers, freed, requests = [], [], []
        response = {'ok': True, 'result': ['Fixture']}
        def call(action, data):
            requests.append((action, json.loads(data)))
            buffer = ctypes.create_string_buffer(json.dumps(response).encode())
            buffers.append(buffer)
            return ctypes.addressof(buffer)
        def free(pointer):
            freed.append(pointer)
        library = SimpleNamespace(LogisticsCloud=call, LogisticsCloudFree=free)
        with patch('ctypes.CDLL', return_value=library):
            client = CloudClient(library='fixture-only')
        self.assertEqual(client.request('list', remote='Fixture'), ['Fixture'])
        response.clear()
        response.update(ok=False, error='Synthetic failure')
        with self.assertRaisesRegex(ValueError, 'Synthetic failure'):
            client.request('list', remote='Fixture')
        self.assertEqual(len(freed), 2)
        with self.assertRaises(ValueError):
            client.request('core/command')
        self.assertEqual(len(requests), 2)

class MultiPackagePrivacyTests(unittest.TestCase):
    def setUp(self):
        for name in ('_package_records', '_package_privacy', '_session_privacy', '_state_epoch'):
            self.addCleanup(setattr, CloudClient, name, getattr(CloudClient, name))
        CloudClient._package_records = ()
        CloudClient._package_privacy = {}
        CloudClient._session_privacy = None
        CloudClient._state_epoch = -1

    def test_saved_and_two_session_packages_keep_distinct_resume_gates(self):
        client = CloudClient.__new__(CloudClient)
        saved = dict(package_name='Personal.zip', saved=True, remotes=['Main'])
        first = dict(package_name='Legacy.zip', saved=False, remotes=['Old'])
        second = dict(package_name='Work.zip', saved=False, remotes=['Work'])
        client.publish_credentials('import', dict(package_name='Legacy.zip', session_only=True, password='one'),
                                   dict(epoch=1, packages=[saved, first]))
        gate = client.session_privacy
        client.publish_credentials('vault_open', {}, dict(epoch=2, packages=[saved, first]))
        self.assertIs(client.session_privacy, gate)
        client.publish_credentials('import', dict(package_name='Work.zip', session_only=True, password='two'),
                                   dict(epoch=3, packages=[saved, first, second]))
        self.assertEqual(len(client.session_privacies), 2)
        self.assertTrue(client.session_privacies[0].verify('one'))
        self.assertTrue(client.session_privacies[1].verify('two'))
        client.publish_credentials('import', dict(package_name='Third.zip', session_only=False),
                                   dict(epoch=4, packages=[saved, first, second, dict(package_name='Third.zip', saved=True, remotes=['Third'])]))
        self.assertEqual(len(client.session_privacies), 2)
        client.publish_credentials('clear', {}, dict(epoch=5, packages=[]))
        self.assertFalse(client.session_privacies)
        self.assertFalse(client.package_records)

    def test_stale_native_state_cannot_replace_a_newer_package_list(self):
        client = CloudClient.__new__(CloudClient)
        latest = dict(package_name='Personal.zip', saved=True, remotes=['Main'])
        client.publish_credentials('vault_open', {}, dict(epoch=4, packages=[latest]))
        client.publish_credentials('vault_open', {}, dict(epoch=3, packages=[]))
        self.assertEqual(client.package_records, (latest,))
