"""Optional rebuilt host bridge integration; only synthetic in-memory remotes."""
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
    def test_regular_and_crypt_direct_readers(self):
        from PIL import Image
        client = CloudClient(library=os.environ['LOGISTICS_REMOTE_BRIDGE'])
        self.addCleanup(client.clear)
        with TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            upload = root / 'upload'
            upload.mkdir()
            (upload / 'note.txt').write_bytes(b'native remote sentinel')
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
            for remote in ('Cloud', 'Secret'):
                identity = client.connection_identity(remote)
                client.request('mirror_sync', remote=remote, path='folder', identity=identity,
                    run=uuid4().hex, local_path=str(upload), push=True, decrypted=True)
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
