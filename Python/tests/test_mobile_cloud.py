"""Private-copy and scoped credential boundaries; native engine has its own gates."""
import base64
import ctypes
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from commonUtils.runtime.document_access import LocalDocuments
from logisticsmobile.cloud import CloudClient, Downloads, download_name, PACKAGE_LIMIT


class MobileCloudTests(unittest.TestCase):
    def test_mobile_cloud_downloads_recover_only_complete_private_copies(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            store = Downloads(root / 'Downloads')
            with patch('os.link', side_effect=PermissionError('No hard links')):
                first = store.save('fixture.txt', b'private copy')
                second = store.save('fixture.txt', b'another copy')
            self.assertNotEqual(first, second)
            self.assertEqual(len(Downloads(store.root).items()), 2)
            (first.parent / '.complete').unlink()
            self.assertEqual(store.items(), [second])
            first.unlink()
            first.symlink_to(second)
            (first.parent / '.complete').write_text(first.name)
            self.assertEqual(store.items(), [second])
            with self.assertRaises(ValueError):
                store.save('.complete', b'reserved')
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
