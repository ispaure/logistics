import base64
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from features.rclone import executable, session
from local_crypt_fixture import crypt_fixture
from logisticsmobile.cloud import CloudClient
from logisticsmobile.localcrypt import LocalCryptCopies

import os
import unittest

@unittest.skipUnless(os.environ.get("LOGISTICS_MOBILE_BRIDGE"), "Build the host mobile bridge and set LOGISTICS_MOBILE_BRIDGE")
class MobileCryptNativeTests(unittest.TestCase):
    def test_desktop_ciphertext_mobile_text_and_metadata_round_trip(self):
        client = CloudClient(library=os.environ['LOGISTICS_MOBILE_BRIDGE'])
        with TemporaryDirectory() as directory, crypt_fixture(directory, executable.get_rclone_path()) as f:
            settings = dict(session.credentials(f.context)['Secret'], remote='Cloud:offline-fixture')
            package = BytesIO()
            with ZipFile(package, 'w') as archive:
                archive.writestr('Cloud.txt', '[Cloud]\ntype=memory\n')
                archive.writestr('Secret.txt', '[Secret]\n' + ''.join(f'{k}={v}\n' for k,v in settings.items()))
            client.request('import', package=base64.b64encode(package.getvalue()).decode(), password='', package_name='Fixture.zip', session_only=True)
            identity = sha256(json.dumps(settings, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            copies = LocalCryptCopies(f.root / 'mobile-ciphertext', client)
            key = 'a' * 32
            folder = copies.root / key
            folder.mkdir()
            encrypted = f.provider.encrypted_path('note.md')
            (folder / 'data').write_bytes(encrypted.read_bytes())
            (folder / 'record.json').write_text(json.dumps(dict(remote='Secret', encrypted_path=encrypted.name, identity=identity)))
            assert copies.items() == [(key, 'note.md')]
            assert copies.open(key).page(0) == ('text', f.original.decode())
            saved = copies.save(copies.open(key), '# Edited on mobile\n')
            assert saved.text == '# Edited on mobile\n'
            assert copies.open(key).text == saved.text
            assert b'Edited on mobile' not in (folder / 'data').read_bytes()
            from commonUtils.archives.zip_access import ArchivePasswordError
            comic_key = 'b' * 32
            comic = copies.root / comic_key
            comic.mkdir()
            encrypted = f.provider.encrypted_path('encrypted.cbz')
            original = encrypted.read_bytes()
            (comic / 'data').write_bytes(original)
            (comic / 'record.json').write_text(json.dumps(dict(remote='Secret', encrypted_path=encrypted.name, identity=identity)))
            for password in ('', 'wrong'):
                try:
                    copies.open(comic_key, password=password)
                except ArchivePasswordError:
                    pass
                else:
                    raise AssertionError('Wrong inner ZIP password accepted')
            assert copies.open(comic_key, password='synthetic-archive-password').page(0) == ('image', f.image)
            assert (comic / 'data').read_bytes() == original
            reader = copies.open(comic_key, password='synthetic-archive-password')
            updated = copies.save_metadata(reader, {'Title': 'Mobile metadata sentinel'})
            assert updated.comic.info.get_field('Title') == 'Mobile metadata sentinel'
            assert updated.page(0) == ('image', f.image)
            try:
                copies.open(comic_key, password='wrong')
            except ArchivePasswordError:
                pass
            else:
                raise AssertionError('Inner password removed by metadata save')
            from books_fixture import make_book
            from commonUtils.archives.zip_access import open_archive
            for index, password in enumerate(('', 'synthetic-archive-password')):
                source = BytesIO()
                make_book(source)
                if password:
                    encrypted_source = BytesIO()
                    with ZipFile(BytesIO(source.getvalue())) as incoming, open_archive(encrypted_source, 'w', password=password) as outgoing:
                        for member in incoming.infolist():
                            outgoing.writestr(member.filename, incoming.read(member))
                    source = encrypted_source
                f.provider.command('rcat', 'book.epub', input_data=source.getvalue(), limit=0)
                encrypted = f.provider.encrypted_path('book.epub')
                book_key = str(index + 3) * 32
                folder = copies.root / book_key
                folder.mkdir()
                (folder / 'data').write_bytes(encrypted.read_bytes())
                (folder / 'record.json').write_text(json.dumps(dict(remote='Secret', encrypted_path=encrypted.name, identity=identity)))
                reader = copies.open(book_key, password=password)
                updated = copies.save_metadata(reader, {'title': ['Mobile EPUB sentinel'], 'creator': ['New author']})
                assert updated.book.values('title') == ['Mobile EPUB sentinel']
                assert copies.open(book_key, password=password).book.values('creator') == ['New author']
                assert b'Mobile EPUB sentinel' not in (folder / 'data').read_bytes()
            client.clear()
            try:
                copies.open(key)
            except ValueError:
                pass
            else:
                raise AssertionError('Forgotten credentials still decrypt')

    def test_large_archive_streamed_move_preview_and_metadata(self):
        from logisticsmobile.file_resources import CryptFiles, ManagedCopies, DownloadedCryptFile
        from logisticsmobile.browser_preview import callbacks
        from commonUtils.runtime.local_files import LocalFiles
        from commonUtils.runtime.resource_mutations import move_resource
        from local_crypt_fixture import crypt_fixture
        client = CloudClient(library=os.environ['LOGISTICS_MOBILE_BRIDGE'])
        with TemporaryDirectory() as directory, crypt_fixture(directory, executable.get_rclone_path()) as f:
            settings = dict(session.credentials(f.context)['Secret'], remote='Cloud:large-fixture')
            package = BytesIO()
            with ZipFile(package, 'w') as archive:
                archive.writestr('Cloud.txt', '[Cloud]\ntype=memory\n')
                archive.writestr('Secret.txt', '[Secret]\n' + ''.join(f'{k}={v}\n' for k,v in settings.items()))
            client.request('import', package=base64.b64encode(package.getvalue()).decode(), password='', package_name='Fixture.zip', session_only=True)
            local_root = Path(directory) / 'large-plain'
            local_root.mkdir()
            source = local_root / 'large.cbz'
            with ZipFile(source, 'w') as archive:
                archive.writestr('page.png', f.image)
                # A single unrelated member larger than the old whole-file cap.
                with archive.open('payload.bin', 'w') as output:
                    for _ in range(40):
                        output.write(b'x' * 1024 * 1024)
            local = LocalFiles(local_root)
            crypt = CryptFiles(Path(directory) / 'managed', client, 'Secret')
            move_resource(local, 'large.cbz', crypt, 'large.cbz')
            self.assertFalse(source.exists())
            copies = ManagedCopies(crypt)
            reader = copies.open('large.cbz')
            self.assertTrue(reader.streaming)
            self.assertEqual(reader.page(0), ('image', f.image))
            preview, details = callbacks(crypt, client)
            self.assertTrue(preview(crypt.entry('large.cbz'), (160, 160), lambda: False).startswith(b'\x89PNG'))
            self.assertIn(('Pages', 1), details(crypt.entry('large.cbz'), lambda: False))
            updated = copies.save_metadata(reader, {'Title': 'Large streamed metadata'})
            self.assertEqual(updated.comic.info.get_field('Title'), 'Large streamed metadata')
            self.assertEqual(updated.page(0), ('image', f.image))
            # Offline downloads use the same streaming rewrap source.
            offline = LocalCryptCopies(Path(directory) / 'offline', client)
            key = 'c' * 32
            folder = offline.root / key
            folder.mkdir()
            import shutil
            shutil.copyfile(crypt._locate('large.cbz'), folder / 'data')
            (folder / 'record.json').write_text(json.dumps(crypt.record('large.cbz')))
            downloaded = DownloadedCryptFile(offline, key)
            move_resource(downloaded, downloaded.name, crypt, 'downloaded.cbz')
            self.assertFalse(folder.exists())
            self.assertEqual(copies.open('downloaded.cbz').page(0), ('image', f.image))
            move_resource(crypt, 'downloaded.cbz', local, 'back.cbz')
            with ZipFile(local_root / 'back.cbz') as archive, archive.open('payload.bin') as member:
                digest = sha256()
                while chunk := member.read(1024 * 1024):
                    digest.update(chunk)
                self.assertEqual(digest.hexdigest(), sha256(b'x' * 40 * 1024 * 1024).hexdigest())
            cached = copies.open('large.cbz')
            client.clear()
            with self.assertRaisesRegex(ValueError, 'locked'):
                cached.page(0)
