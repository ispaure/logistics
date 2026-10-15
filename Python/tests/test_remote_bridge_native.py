"""Optional rebuilt host bridge integration; only synthetic in-memory remotes."""
from io import BytesIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4
from zipfile import ZipFile

from commonUtils.runtime.document_access import LocalDocuments
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


if __name__ == '__main__':
    unittest.main()
