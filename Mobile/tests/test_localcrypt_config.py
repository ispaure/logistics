from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from commonUtils.archives.zip_access import ArchivePasswordError
from commonUtils.runtime.local_files import LocalFiles
from features.rclone.localcrypt.mobile.resources import CryptFiles, ManagedCopies
from features.rclone.localcrypt.mobile.copies import LocalCryptCopies


class LocalCryptConfigurationTests(unittest.TestCase):
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
            provider.collection_storage_root = None
            def mapping(path, directory=False, decode=False):
                self.assertNotEqual(path, partial.name)
                if path == vanished.name and decode:
                    vanished.unlink(missing_ok=True)
                return path
            provider.mapping = mapping
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
            provider = self.provider(Path(directory), {'remoteConfig.ini': b'[LogisticsZIP]\narchive_password=fixture-only\n'})
            copies = ManagedCopies(provider)
            reader = object()
            with patch.object(LocalCryptCopies, 'open', side_effect=[ArchivePasswordError('Locked archive'), reader]) as opened:
                self.assertIs(copies.open('Comics/book.cbz'), reader)
                self.assertEqual(opened.call_args.kwargs['password'], 'fixture-only')
            with patch.object(LocalCryptCopies, 'open', return_value=reader), patch.object(provider, 'archive_password', side_effect=AssertionError('Unneeded lookup')):
                self.assertIs(copies.open('plain.cbz'), reader)
            with patch.object(LocalCryptCopies, 'open', side_effect=ArchivePasswordError('Locked archive')) as opened:
                with self.assertRaises(ArchivePasswordError):
                    copies.open('book.cbz', password='explicit-fixture')
                self.assertEqual(opened.call_count, 1)
