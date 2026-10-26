"""Offline ciphertext bookkeeping and RAM-only portable readers."""
import base64
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from features.rclone.localcrypt.mobile.copies import LocalCryptCopies
from services.documents.readers import PrivateReader
from books_fixture import make_book

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')


def seed_offline_copy(copies, data=b'opaque-original'):
    """Seed a pre-existing offline record without a remote download API."""
    import json
    from uuid import uuid4
    key = uuid4().hex
    folder = copies.root / key
    folder.mkdir()
    (folder / 'data').write_bytes(data)
    (folder / 'record.json').write_text(json.dumps(dict(
        remote='Secret', encrypted_path='encoded', identity='a' * 64)))
    return key


class MobileLocalCryptTests(unittest.TestCase):
    def test_ini_reader_is_editable_memory_only_and_preserves_line_endings(self):
        data = b'[Settings]\r\nvalue=private-sentinel\r\n'
        with patch.object(Path, 'open', side_effect=AssertionError('No plaintext files')):
            reader = PrivateReader('Settings.INI', data)
            self.assertTrue(reader.editable)
            self.assertEqual(reader.page(0), ('text', '[Settings]\nvalue=private-sentinel\n'))
            self.assertEqual(reader.text_snapshot.encode(reader.text), data)
        with self.assertRaises(ValueError):
            PrivateReader('large.ini', b'x' * (1024 * 1024 + 1))

    def test_text_and_comic_reads_are_memory_only(self):
        reader = PrivateReader('note.md', b'# private sentinel')
        self.assertEqual(reader.page(0), ('text', '# private sentinel'))
        data = BytesIO()
        with ZipFile(data, 'w') as archive:
            archive.writestr('page10.png', PNG)
            archive.writestr('page2.webp', base64.b64decode('UklGRhwAAABXRUJQVlA4TA8AAAAvAYAAEAcQ/Y8CBiKi/wEA'))
        with patch.object(Path, 'open', side_effect=AssertionError('Reader must not open disk files')):
            reader = PrivateReader('comic.cbz', data.getvalue())
            self.assertEqual(reader.pages, ['page2.webp', 'page10.png'])
            self.assertEqual(reader.page(1), ('image', PNG))
            self.assertEqual(reader.page(0), ('image', base64.b64decode('UklGRhwAAABXRUJQVlA4TA8AAAAvAYAAEAcQ/Y8CBiKi/wEA')))
        with self.assertRaises(ValueError):
            PrivateReader('note.md', b'x' * (1024 * 1024 + 1))

    def test_epub_source_reads_without_plaintext_files(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / 'fixture.epub'
            make_book(source)
            data = source.read_bytes()
            source.unlink()
            with patch.object(Path, 'open', side_effect=AssertionError('No plaintext filesystem reads')):
                reader = PrivateReader('fixture.epub', data)
                kind, text = reader.page(0)
                self.assertEqual(kind, 'text')
                self.assertTrue(text.strip())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_existing_ciphertext_storage_and_locked_listing(self):
        import os
        record = dict(remote='Secret', encrypted_path='encrypted-name', identity='a' * 64)
        class Client:
            generation = 0
            locked = False
            failed = False
            def request(self, action, **values):
                if self.locked:
                    raise ValueError('Unlock credentials')
                if action == 'crypt_describe':
                    return 'note.md'
                if action == 'crypt_decode':
                    return dict(name='note.md', data=base64.b64encode(b'# secret sentinel').decode())
                raise AssertionError(action)
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            client = Client()
            copies = LocalCryptCopies(root, client)
            key = seed_offline_copy(copies)
            self.assertEqual(copies.items(), [(key, 'note.md')])
            self.assertEqual(copies.open(key).page(0), ('text', '# secret sentinel'))
            for file in root.rglob('*'):
                if file.is_file():
                    self.assertNotIn(b'secret sentinel', file.read_bytes())
                    self.assertNotIn(b'note.md', file.read_bytes())
            client.locked = True
            self.assertIn('Locked copy', copies.items()[0][1])
            with self.assertRaises(ValueError):
                copies.open(key)
            client.locked = False

    def test_verified_save_conflict_cancellation_and_encoding(self):
        import os
        from commonUtils.runtime.operations import OperationCancelled
        class Client:
            generation = 0
            cancel_after_encode = False
            fail = False
            def request(self, action, **values):
                if action == 'crypt_describe':
                    return 'note.md'
                if action == 'crypt_encode':
                    self.saved = base64.b64decode(values['data'])
                    os.write(values['fd'], b'opaque-updated')
                    if self.cancel_after_encode:
                        cancelled[0] = True
                    return True
                if action == 'crypt_decode':
                    content = os.read(values['fd'], 100)
                    data = (b'bad verification' if self.fail else self.saved) if content == b'opaque-updated' else b'\xef\xbb\xbf# Original\r\n'
                    return dict(name='note.md', data=base64.b64encode(data).decode())
                raise AssertionError(action)
        with TemporaryDirectory() as directory:
            client = Client()
            cancelled = [False]
            copies = LocalCryptCopies(Path(directory).resolve(), client)
            key = seed_offline_copy(copies)
            reader = copies.open(key)
            updated = copies.save(reader, '# Edited\n')
            self.assertEqual(client.saved, b'\xef\xbb\xbf# Edited\r\n')
            self.assertEqual(updated.text, '# Edited\n')
            with self.assertRaisesRegex(ValueError, 'changed'):
                copies.save(reader, 'stale')
            with self.assertRaises(OperationCancelled):
                copies.save(updated, 'cancelled', cancelled=lambda: True)
            with self.assertRaises(ValueError):
                copies.save(updated, '\ud800')
            client.cancel_after_encode = True
            with self.assertRaises(OperationCancelled):
                copies.save(updated, 'cancel midway', cancelled=lambda: cancelled[0])
            client.cancel_after_encode = False
            client.fail = True
            with self.assertRaisesRegex(ValueError, 'verification failed'):
                copies.save(updated, 'bad')
            self.assertEqual((copies.root / key / 'data').read_bytes(), b'opaque-updated')
            self.assertEqual(sorted(p.name for p in (copies.root / key).iterdir()), ['data', 'record.json'])
            from unittest.mock import patch
            collision = copies.root / key / 'existing-stage'
            collision.write_bytes(b'belongs to someone else')
            with patch.object(copies, '_temporary', return_value=collision):
                with self.assertRaises(FileExistsError): copies.save(updated, 'collision')
            self.assertEqual(collision.read_bytes(), b'belongs to someone else')


    def test_metadata_plan_and_verified_transaction_preserve_comic_pages(self):
        import os
        from services.documents.metadata import rewrite_metadata
        original = BytesIO()
        with ZipFile(original, 'w') as archive:
            archive.writestr('page.png', PNG)
            archive.writestr('ComicInfo.xml', b'<ComicInfo><Title>Before</Title><Pages><Page Image="0" Bookmark="keep"/></Pages></ComicInfo>')
        class Client:
            generation = 0
            corrupt = False
            data = original.getvalue()
            def request(self, action, **values):
                if action == 'crypt_describe':
                    return 'comic.cbz'
                if action == 'crypt_decode':
                    return dict(name='comic.cbz', data=base64.b64encode(self.data).decode())
                if action == 'crypt_metadata':
                    self.password = values['password']
                    result = BytesIO()
                    with ZipFile(BytesIO(self.data)) as incoming, ZipFile(result, 'w') as output:
                        rewrite_metadata(incoming, output, values['member'], base64.b64decode(values['data']))
                        if self.corrupt:
                            output.writestr('unexpected.txt', b'bad')
                    self.data = result.getvalue()
                    os.write(values['output_fd'], b'updated ciphertext')
                    return True
                raise AssertionError(action)
        with TemporaryDirectory() as directory:
            client = Client()
            copies = LocalCryptCopies(Path(directory).resolve(), client)
            key = seed_offline_copy(copies)
            reader = copies.open(key, password='session-only')
            updated = copies.save_metadata(reader, {'Title': 'Edited'})
            self.assertEqual(client.password, 'session-only')
            self.assertEqual(updated.comic.info.get_field('Title'), 'Edited')
            self.assertEqual(updated.page(0), ('image', PNG))
            self.assertIn(b'Bookmark="keep"', updated.comic.info.to_bytes())
            with self.assertRaisesRegex(ValueError, 'changed'):
                copies.save_metadata(reader, {'Title': 'stale'})
            client.corrupt = True
            with self.assertRaisesRegex(ValueError, 'verification'):
                copies.save_metadata(updated, {'Title': 'Rejected'})
            self.assertEqual((copies.root / key / 'data').read_bytes(), b'updated ciphertext')
            self.assertFalse(list(copies.root.rglob('.save-*')))

    def test_malformed_comic_metadata_does_not_prevent_reading(self):
        content = BytesIO()
        with ZipFile(content, 'w') as archive:
            archive.writestr('page.png', PNG)
            archive.writestr('ComicInfo.xml', b'<broken')
        reader = PrivateReader('comic.cbz', content.getvalue())
        self.assertEqual(reader.page(0), ('image', PNG))
        with self.assertRaises(Exception):
            reader.comic


class LocalAdapterTests(unittest.TestCase):
    def test_local_text_late_cancel_and_external_write_after_save(self):
        from unittest.mock import patch
        from commonUtils.runtime.resources.local import LocalFiles
        from commonUtils.runtime.operations import MutationIncomplete
        from features.text_editor.resources import LocalTextCopies
        with TemporaryDirectory() as directory:
            provider = LocalFiles(directory)
            path = Path(directory) / 'note.txt'
            path.write_bytes(b'old')
            copies = LocalTextCopies(provider)
            reader = copies.open('note.txt')
            replace = provider.replace_created
            cancelled = []
            def publish(*args):
                replace(*args)
                cancelled.append(True)
            with patch.object(provider, 'replace_created', side_effect=publish):
                updated = copies.save(reader, 'new', cancelled=lambda: bool(cancelled))
            self.assertEqual(updated.text, 'new')
            def external(*args):
                replace(*args)
                path.write_bytes(b'external')
            with patch.object(provider, 'replace_created', side_effect=external):
                with self.assertRaises(MutationIncomplete) as caught:
                    copies.save(updated, 'next')
            self.assertTrue(caught.exception.result.destination_published)
            self.assertEqual(path.read_bytes(), b'external')

    def test_transfer_adapter_rejects_consumed_or_closed_source(self):
        from features.rclone.localcrypt.mobile.resources import CryptTransferStream
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'cipher'
            path.write_bytes(b'ciphertext')
            with path.open('rb') as encrypted:
                with CryptTransferStream(b'plain', dict(remote='r', encrypted_path='p', identity='i'), encrypted) as stream:
                    self.assertEqual(stream.transfer_source()[0], encrypted.fileno())
                    stream.read(1)
                    with self.assertRaises(ValueError): stream.transfer_source()
                with self.assertRaises(ValueError): stream.transfer_source()
