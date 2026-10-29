"""Optional rebuilt host bridge integration; only synthetic in-memory remotes."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from io import BytesIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4
from zipfile import ZipFile

from commonUtils.runtime.resources.documents import LocalDocuments
from features.rclone.mobile.cloud import CloudClient
from features.rclone.mobile.remote_readers import RemoteReaders


@unittest.skipUnless(os.environ.get('LOGISTICS_REMOTE_BRIDGE'), 'Set LOGISTICS_REMOTE_BRIDGE to a rebuilt host bridge')
class RemoteNativeBridgeTests(unittest.TestCase):
    def test_service_saved_vault_and_retained_zip_forgetting(self):
        from types import SimpleNamespace
        from features.rclone.mobile.credential_loading import NativeCredentialLoad
        from features.rclone.mobile.credential_retention import NativeCredentialRetention, NativeCredentialForget
        from features.rclone.mobile.credential_packages import CredentialPackages
        from features.rclone.mobile.credential_vault import ProtectedVault
        from features.rclone.mobile.service import native_service

        class Keys:
            def __init__(self):
                self.values = {}
            def create(self, identity, key):
                self.values[identity] = key
                return {}
            def load(self, identity, record):
                return self.values[identity]
            def delete(self, identity):
                self.values.pop(identity, None)

        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            keys = Keys()
            vault = ProtectedVault(root / 'Saved', keys, 'fixture')
            package_vault = ProtectedVault(root / 'Retained', keys, 'fixture')
            client = CloudClient(library=os.environ['LOGISTICS_REMOTE_BRIDGE'], vault=vault)
            self.addCleanup(client.clear)
            credentials = native_service(client).credentials
            source = Path(__file__).resolve().parents[3] / 'mobile_build/rclone_bridge/testdata/credentials-aes256.zip'
            loaded = credentials.load(NativeCredentialLoad(LocalDocuments(), source, True), 'synthetic-fixture-password')
            self.assertTrue(vault.ciphertext.exists())
            credentials.lock()
            restored = credentials.restore()
            self.assertEqual(restored.remotes, loaded.remotes)
            store = CredentialPackages(package_vault, client)
            package = SimpleNamespace(name=source.name, data=source.read_bytes())
            key = credentials.retain(NativeCredentialRetention(store, package, restored.remotes, client.generation))
            grant = credentials.capture(loaded.key)
            credentials.lock()
            self.assertTrue(store.path(key).exists())
            pending = credentials.prepare_load(NativeCredentialLoad(store, key, False), 'synthetic-fixture-password')
            credentials.forget(NativeCredentialForget(lambda: store, store.document_cache_root))
            self.assertEqual(store.items, {})
            self.assertFalse(store.path(key).exists())
            self.assertFalse(vault.ciphertext.exists())
            self.assertFalse(vault.record.exists())
            self.assertFalse(package_vault.record.exists())
            self.assertEqual(keys.values, {})
            self.assertTrue(source.exists())
            with self.assertRaises(ValueError):
                credentials.unlock(pending)
            with self.assertRaises(ValueError):
                grant.check()
            self.assertEqual(credentials.restore().remotes, ())

    def test_regular_and_crypt_direct_readers(self):
        from PIL import Image
        client = CloudClient(library=os.environ['LOGISTICS_REMOTE_BRIDGE'])
        self.addCleanup(client.clear)
        with TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            upload = root / 'upload'
            upload.mkdir()
            (upload / 'note.txt').write_bytes(b'native remote sentinel')
            video_bytes = bytes(range(256)) * 19000
            (upload / 'movie.avi').write_bytes(video_bytes)
            image = BytesIO()
            Image.new('RGB', (24, 32), 'red').save(image, 'PNG')
            (upload / 'page.png').write_bytes(image.getvalue())
            with ZipFile(upload / 'comic.cbz', 'w') as archive:
                archive.writestr('page.png', image.getvalue())
            package = root / 'Synthetic.zip'
            with ZipFile(package, 'w') as archive:
                archive.writestr('Cloud.txt', '[Cloud]\ntype=memory\n')
                archive.writestr('Secret.txt', '[Secret]\ntype=crypt\nremote=Cloud:encrypted\n'
                    'password=kbLdY_D-MRsrDH6_akD3SfOzlJ0VseUk2jfUrywMSTOLmTrSvFOxCkP94a-Ul-w\n')
            client.import_package(LocalDocuments(), package, '', remember=False)
            # The synthetic unencrypted ZIP needs the normal initial resume-password setup.
            gate = client.session_privacy
            self.assertTrue(gate.configure('Synthetic-video-resume'))
            self.assertTrue(gate.authorize(gate.revision))
            for remote in ('Cloud', 'Secret'):
                identity = client.connection_identity(remote)
                client.request('mirror_sync', remote=remote, path='folder', identity=identity,
                    run=uuid4().hex, local_path=str(upload), push=True, decrypted=True)
                # Use VideoContent's actual 4 MiB range policy through the Go
                # library, rather than a permissive Python client double.
                from features.rclone.mobile.service import native_service
                from features.rclone.remote_access import NativeRemoteLocation
                from features.video.playback import VideoContent
                resource = native_service(client).remotes.open(NativeRemoteLocation(remote))
                content = VideoContent(resource, 'folder/movie.avi')
                try:
                    from unittest.mock import patch
                    with patch.object(client, 'request', wraps=client.request) as requests:
                        with content.open() as stream:
                            self.assertEqual(stream.read(4 * 1024 * 1024), video_bytes[:4 * 1024 * 1024])
                            self.assertEqual(stream.read(16), video_bytes[4 * 1024 * 1024:4 * 1024 * 1024 + 16])
                        fetched = [call for call in requests.call_args_list if call.args[0] == 'remote_range']
                        self.assertEqual(len(fetched), 2)
                        with content.open() as rewound:
                            self.assertEqual(rewound.read(32), video_bytes[:32])
                        self.assertEqual(len([call for call in requests.call_args_list
                                              if call.args[0] == 'remote_range']), 2,
                                         'Rewind fetched data already held in memory')
                finally:
                    content.close()
                    resource.close()
                readers = RemoteReaders(client, remote)
                text = readers.open('folder/note.txt')
                self.assertEqual(text.text, 'native remote sentinel')
                self.assertTrue(text.read_only)
                text.source.close()
                comic = readers.open('folder/comic.cbz')
                self.assertEqual(comic.page(0), ('image', image.getvalue()))
                comic.source.close()

    def test_shared_service_reviews_and_executes_native_regular_and_crypt_transfers(self):
        from features.rclone.mobile.service import native_service
        from features.rclone.transfers.mobile.jobs import MirrorJobs
        from features.rclone.transfers.mobile.plan import NativeTransferRequest
        from features.rclone.transfers.transfer_options import TransferOptions
        client = CloudClient(library=os.environ['LOGISTICS_REMOTE_BRIDGE'])
        self.addCleanup(client.clear)
        with TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            upload = root / 'upload'
            upload.mkdir()
            (upload / 'note.txt').write_bytes(b'service transfer fixture')
            package = root / 'Synthetic.zip'
            with ZipFile(package, 'w') as archive:
                archive.writestr('Cloud.txt', '[Cloud]\ntype=memory\n')
                archive.writestr('Secret.txt', '[Secret]\ntype=crypt\nremote=Cloud:encrypted\n'
                    'password=kbLdY_D-MRsrDH6_akD3SfOzlJ0VseUk2jfUrywMSTOLmTrSvFOxCkP94a-Ul-w\n')
            from features.rclone.mobile.credential_loading import NativeCredentialLoad
            loaded = native_service(client).credentials.load(
                NativeCredentialLoad(LocalDocuments(), package, False), '')
            self.assertEqual(set(loaded.remotes), {'Cloud', 'Secret'})
            service = native_service(client).transfers
            store = MirrorJobs(root)
            for remote in ('Cloud', 'Secret'):
                client.request('mirror_sync', remote=remote, path='folder',
                    identity=client.connection_identity(remote), run=uuid4().hex,
                    local_path=str(upload), push=True, decrypted=True)
                job = store.prepare_review(client, remote, 'folder')
                for push, new in ((False, True), (True, False)):
                    prepared = service.review(NativeTransferRequest(store, job, push, new,
                        TransferOptions(copy_links=not job['crypt']), client.generation))
                    self.assertTrue(prepared.review.scan.retired.wait(10))
                    self.assertTrue(prepared.review.approve())
                    self.assertTrue(prepared.review.scan.retired.wait(10))
                    self.assertTrue(prepared.review.approved)
                    service.execute(prepared)
                self.assertTrue(store.target(job).is_dir())
                self.assertIn(job['id'], store.jobs)
                reader = RemoteReaders(client, remote).open('folder/note.txt')
                try:
                    self.assertEqual(reader.data, b'service transfer fixture')
                finally:
                    reader.source.close()
            credentials = native_service(client).credentials
            grant = credentials.capture('Cloud')
            credentials.lock()
            with self.assertRaises(ValueError):
                grant.check()
            reloaded = credentials.load(NativeCredentialLoad(LocalDocuments(), package, False), '')
            self.assertEqual(set(reloaded.remotes), {'Cloud', 'Secret'})
            with self.assertRaises(ValueError):
                grant.check()


if __name__ == '__main__':
    unittest.main()
