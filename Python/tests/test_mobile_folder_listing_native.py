"""Exercise batched LocalCrypt listing through the shipped C/JSON bridge."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import base64
from io import BytesIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from features.rclone import executable, session
from features.rclone.localcrypt.mobile.resources import CryptFiles
from features.rclone.mobile.cloud import CloudClient
from local_crypt_fixture import crypt_fixture


@unittest.skipUnless(os.environ.get('LOGISTICS_MOBILE_BRIDGE'), 'Requires the host mobile bridge')
class FolderListingNativeTests(unittest.TestCase):
    def test_batched_names_keep_nested_paths_and_reject_a_locked_session(self):
        client = CloudClient(library=os.environ['LOGISTICS_MOBILE_BRIDGE'])
        self.addCleanup(client.clear)
        with TemporaryDirectory() as root, crypt_fixture(root, executable.get_rclone_path()) as fixture:
            settings = dict(session.credentials(fixture.context)['Secret'], remote='Cloud:listing-fixture')
            package = BytesIO()
            with ZipFile(package, 'w') as archive:
                archive.writestr('Cloud.txt', '[Cloud]\ntype=memory\n')
                archive.writestr('Secret.txt', '[Secret]\n' + ''.join(f'{key}={value}\n' for key, value in settings.items()))
            client.request('import', package=base64.b64encode(package.getvalue()).decode(),
                password='', package_name='Fixture.zip', session_only=True)
            provider = CryptFiles(Path(root) / 'managed', client, 'Secret')
            folder = provider.root / provider.mapping('books', directory=True)
            folder.mkdir()
            expected = {f'books/page{index}.cbz' for index in range(270)}
            ciphertext_entries = []
            for path in expected:
                child = provider.root / provider.mapping(path)
                child.write_bytes(b'encrypted fixture')
                ciphertext_entries.append((child.name, False))
            subfolder = provider.root / provider.mapping('books/subfolder', directory=True)
            subfolder.mkdir()
            ciphertext_entries.append((subfolder.name, True))
            with patch.object(client, 'request', wraps=client.request) as request:
                rows = provider.list('books')
                batches = [call.kwargs['entries'] for call in request.call_args_list
                           if call.args[0] == 'crypt_paths']
                self.assertLessEqual(len(batches), 4, 'Listing should coalesce ciphertext names')
                decoded_entries = []
                for batch in batches:
                    self.assertTrue(1 <= len(batch) <= 256)
                    self.assertLessEqual(sum(2 * len(entry['path'].encode('utf-8')) + 64
                                             for entry in batch), 24 * 1024)
                    decoded_entries.extend((entry['path'], entry['directory']) for entry in batch)
                self.assertCountEqual(decoded_entries, ciphertext_entries)
            self.assertCountEqual([row['path'] for row in rows], expected | {'books/subfolder'})
            self.assertTrue(rows[0]['directory'])
            client.clear()
            with self.assertRaises(ValueError):
                provider.list('books')
