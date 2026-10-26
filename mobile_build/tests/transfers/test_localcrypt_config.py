from contextlib import contextmanager
from io import BytesIO
import base64
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from commonUtils.archives.zip_access import ArchivePasswordError
from commonUtils.runtime.resources.local import LocalFiles
from features.rclone.localcrypt.mobile.resources import CryptFiles, ManagedCopies
from features.rclone.localcrypt.mobile.copies import LocalCryptCopies


class LocalCryptConfigurationTests(unittest.TestCase):
    def listing_provider(self, root):
        def request(action, **values):
            if action == 'crypt_path':
                return dict(identity='a' * 64, path=values['path'])
            self.assertEqual(action, 'crypt_paths')
            return [entry['path'] for entry in values['entries']]
        return CryptFiles(root, SimpleNamespace(request=request, generation=0), 'Secret')

    def capture_encodes(self, provider):
        calls = []
        request = provider.client.request
        def encode(action, **values):
            if action != 'crypt_encode':
                return request(action, **values)
            calls.append(base64.b64decode(values['data']))
            os.write(values['fd'], b'opaque ciphertext fixture')
            return True
        provider.client.request = encode
        return calls

    def test_create_file_consumes_short_reads_before_native_encoding(self):
        class ShortReader(BytesIO):
            def read(self, size=-1):
                return super().read(min(size, 3))
        with TemporaryDirectory() as directory:
            provider = self.listing_provider(directory)
            encoded = self.capture_encodes(provider)
            content = b'Complete short-read input including trailing bytes.'
            provider.create_file('note.md', ShortReader(content))
            self.assertEqual(encoded, [content])
            self.assertEqual(provider._locate('note.md').read_bytes(), b'opaque ciphertext fixture')
            self.assertFalse(list(provider.root.glob('.create-*')))

    def test_create_file_rejects_incomplete_or_oversize_input_before_encoding(self):
        class WouldBlock:
            def read(self, size):
                return None
        class ShortReader(BytesIO):
            def read(self, size=-1):
                return super().read(min(size, 65536))
        for source, error in ((WouldBlock(), BlockingIOError),
                              (ShortReader(b'x' * (1024 * 1024 + 1)), ValueError)):
            with self.subTest(error=error.__name__), TemporaryDirectory() as directory:
                provider = self.listing_provider(directory)
                encoded = self.capture_encodes(provider)
                with self.assertRaises(error):
                    provider.create_file('note.md', source)
                self.assertEqual(encoded, [])
                self.assertEqual(list(provider.root.iterdir()), [])

    def test_listing_rejects_links_shared_files_and_special_files(self):
        from commonUtils.runtime.operations import OperationCancelled
        with TemporaryDirectory() as directory:
            provider = self.listing_provider(directory)
            target = provider.root / 'original'
            target.write_bytes(b'fixture')
            linked = provider.root / 'linked'
            for create in (lambda: linked.symlink_to(target), lambda: os.link(target, linked)):
                create()
                with self.assertRaises(ValueError):
                    provider.list()
                linked.unlink()
            if hasattr(os, 'mkfifo'):
                os.mkfifo(linked)
                with self.assertRaises(ValueError):
                    provider.list()
                linked.unlink()
            with self.assertRaises(OperationCancelled):
                provider.list(cancelled=lambda: True)

    def test_listing_rechecks_parent_if_replaced_during_name_decode(self):
        with TemporaryDirectory() as directory:
            provider = self.listing_provider(directory)
            parent = provider.root / 'folder'
            parent.mkdir()
            (parent / 'file').write_bytes(b'fixture')
            original = provider.client.request
            def request(action, **values):
                if action == 'crypt_paths':
                    parent.rename(provider.root / 'moved')
                    parent.symlink_to(provider.root / 'moved', target_is_directory=True)
                return original(action, **values)
            provider.client.request = request
            with self.assertRaises(ValueError):
                provider.list('folder')

    def test_nested_listing_decodes_only_basenames_without_opening_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / 'parent' / 'nested'
            folder.mkdir(parents=True)
            (folder / 'encoded-file').write_bytes(b'ciphertext fixture')
            provider = object.__new__(CryptFiles)
            LocalFiles.__init__(provider, root)
            from features.rclone.access import ResourceAccess
            from features.rclone.service import CredentialGrant
            provider._access = ResourceAccess(CredentialGrant('fixture', lambda: False))
            provider.collection_storage_root = None
            provider.mapping = lambda path, directory=False, decode=False: path
            provider.remote, provider.identity = 'Secret', 'a' * 64
            def request(action, **values):
                self.assertEqual(action, 'crypt_paths')
                self.assertEqual(values['entries'], [dict(path='encoded-file', directory=False)])
                return ['Book.epub']
            provider.client = SimpleNamespace(request=request, generation=0)
            with patch.object(provider, 'open', side_effect=AssertionError('Content read')):
                rows = provider.list('parent/nested')
            self.assertEqual(rows[0]['name'], 'Book.epub')
            self.assertEqual(rows[0]['path'], 'parent/nested/Book.epub')
            for invalid in ['other/Book.epub', '../Book.epub', '']:
                provider.client = SimpleNamespace(request=lambda *a, **k: [invalid])
                with self.assertRaises(ValueError):
                    provider.list('parent/nested')

    def test_listing_hides_rclone_partial_files_and_tolerates_removed_entries(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'finished.md').write_bytes(b'ciphertext fixture')
            partial = root / 'encoded-name.a1b2c3d4.partial'
            partial.write_bytes(b'incomplete ciphertext')
            vanished = root / 'removed.md'
            vanished.write_bytes(b'old ciphertext')
            provider = object.__new__(CryptFiles)
            LocalFiles.__init__(provider, root)
            from features.rclone.access import ResourceAccess
            from features.rclone.service import CredentialGrant
            provider._access = ResourceAccess(CredentialGrant('fixture', lambda: False))
            provider.collection_storage_root = None
            def mapping(path, directory=False, decode=False):
                self.assertNotEqual(path, partial.name)
                if path == vanished.name and decode:
                    vanished.unlink(missing_ok=True)
                return path
            provider.mapping = mapping
            provider.remote, provider.identity = 'Secret', 'a' * 64
            def request(action, **values):
                self.assertEqual(action, 'crypt_paths')
                return [mapping(item['path'], item['directory'], decode=True) for item in values['entries']]
            provider.client = SimpleNamespace(request=request, generation=0)
            self.assertEqual([row['name'] for row in provider.list()], ['finished.md'])
            self.assertTrue(partial.exists())

    def provider(self, root, configs):
        provider = object.__new__(CryptFiles)
        LocalFiles.__init__(provider, root)
        provider.client = SimpleNamespace()
        @contextmanager
        def open(path):
            if path not in configs:
                raise FileNotFoundError(path)
            with BytesIO(configs[path]) as source:
                yield source
        provider.open = open
        return provider

    def test_nearest_ancestor_config_and_empty_section_stop_inheritance(self):
        with TemporaryDirectory() as directory:
            configs = {'remoteConfig.ini': b'[LogisticsZIP]\narchive_password=fixture-only\n'}
            provider = self.provider(Path(directory), configs)
            self.assertEqual(provider.archive_password('Books/Series/file.cbz'), 'fixture-only')
            configs['Books/remoteConfig.ini'] = b'[DEFAULT]\narchive_password=ignored\n[LogisticsZIP]\n'
            self.assertIsNone(provider.archive_password('Books/Series/file.cbz'))
            configs['Books/remoteConfig.ini'] = b'[Other]\nvalue=unrelated\n'
            self.assertEqual(provider.archive_password('Books/Series/file.cbz'), 'fixture-only')

    def test_config_lookup_is_bounded_and_errors_do_not_echo_contents(self):
        with TemporaryDirectory() as directory:
            configs = {'remoteConfig.ini': b'[LogisticsZIP]\narchive_password=fixture-only\nmalformed'}
            provider = self.provider(Path(directory), configs)
            with self.assertRaises(ValueError) as error:
                provider.archive_password('book.cbz')
            self.assertNotIn('fixture-only', str(error.exception))
            configs['remoteConfig.ini'] = b'x' * 65537
            with self.assertRaises(ValueError):
                provider.archive_password('book.cbz')

    def test_managed_open_retries_with_config_only_after_native_unlock_requires_it(self):
        with TemporaryDirectory() as directory:
            provider = LocalFiles(Path(directory))
            (provider.root / 'book.cbz').write_bytes(b'archive fixture')
            provider.archive_password = Mock(return_value='fixture-only')
            copies = ManagedCopies(provider)
            def reader():
                return SimpleNamespace(editable=False, read_only=False, kind='.cbz', name='book.cbz')
            with patch('services.documents.readers.PrivateReader', side_effect=[ArchivePasswordError('Locked archive'), reader()]) as opened:
                result = copies.open('book.cbz')
                self.addCleanup(result.source.close)
                self.assertEqual(opened.call_args.kwargs['source'].password, 'fixture-only')
            with patch('services.documents.readers.PrivateReader', return_value=reader()), patch.object(provider, 'archive_password', side_effect=AssertionError('Unneeded lookup')):
                result = copies.open('book.cbz')
                self.addCleanup(result.source.close)
            with patch('services.documents.readers.PrivateReader', side_effect=ArchivePasswordError('Locked archive')) as opened:
                with self.assertRaises(ArchivePasswordError):
                    copies.open('book.cbz', password='explicit-fixture')
                self.assertEqual(opened.call_count, 1)
