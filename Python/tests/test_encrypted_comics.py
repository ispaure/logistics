"""Encrypted comics preserve decrypted results and never modify on auth failure."""

from datetime import datetime
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile
import pyzipper
from PIL import Image

from commonUtils.zip_access import ArchivePasswordError, archive_manifest, open_archive, is_encrypted
from features.comics.cbz import CBZFile, compress_selected_cbz
from features.comics.library import ComicDocument
from features.comics.pages import ComicPages
from features.comics.catalog import LibraryCatalog
from features.comics.metadata import comic_info_xml_replace_author
from features.comics.compression_stats import CompressionLog
from services.zip_passwords import clear_passwords, configured_password, resolve_password


class EncryptedComicTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        clear_passwords()
        self.addCleanup(clear_passwords)
        self.password = 'test-only-%-é'
        self.config = self.root / 'remoteConfig.ini'
        self.configure(self.password)
        self.path = self.root / 'nested' / 'comic.cbz'
        self.path.parent.mkdir()
        image = Image.new('RGB', (80, 120), 'orange')
        png = BytesIO()
        image.save(png, 'PNG')
        gif = BytesIO()
        image.save(gif, 'GIF', save_all=True, append_images=[Image.new('RGB', image.size, 'blue')], duration=100)
        self.entries = {'pages/1.png': png.getvalue(), 'pages/2.gif': gif.getvalue(),
                        'ComicInfo.xml': b'<ComicInfo><Writer>Original</Writer><Series>Private series</Series></ComicInfo>',
                        'notes.txt': b'Sidecar'}

    def configure(self, password):
        self.config.write_text('[LogisticsZIP]\narchive_password = ' + password + '\n', encoding='utf-8')

    def archive(self, path=None, password='default', entries=None):
        path = path or self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        password = self.password if password == 'default' else password
        with open_archive(path, 'w', password=password) as archive:
            for name, data in (entries or self.entries).items():
                archive.writestr(name, data)
        return path

    def test_nearest_section_empty_override_unrelated_config_and_percent_password(self):
        unrelated = self.path.parent / 'remoteConfig.ini'
        unrelated.write_text('[LogisticsComics]\nlibraries = A\n')
        self.assertEqual(configured_password(self.path), self.password)
        unrelated.write_text('[LogisticsZIP]\narchive_password = closer\n')
        self.assertEqual(configured_password(self.path), 'closer')
        unrelated.write_text('[LogisticsZIP]\narchive_password =\n')
        self.assertIsNone(configured_password(self.path))
        unrelated.write_text('[LogisticsZIP]\n')
        self.assertIsNone(configured_password(self.path))

    def test_reader_metadata_cover_and_bytes_open_with_inherited_password(self):
        self.archive()
        before = self.path.read_bytes()
        document = ComicDocument(self.path)
        self.assertEqual(document.info.get_field('Writer'), 'Original')
        pages = ComicPages(self.path, document)
        self.assertEqual(pages.read_page(0)[0], self.entries['pages/1.png'])
        with Image.open(BytesIO(pages.cover())) as image:
            self.assertEqual(image.size, (80, 120))
        self.assertEqual(self.path.read_bytes(), before)

    def test_wrong_config_raises_and_session_password_never_changes_ini(self):
        self.archive()
        self.configure('wrong')
        before_config = self.config.read_bytes()
        with self.assertRaises(ArchivePasswordError):
            ComicDocument(self.path)
        unlocked = ComicDocument(self.path, password=self.password)
        self.assertEqual(unlocked.info.get_field('Writer'), 'Original')
        self.assertEqual(ComicDocument(self.path).password, self.password.encode())
        self.assertEqual(self.config.read_bytes(), before_config)
        with self.assertRaises(ArchivePasswordError):
            resolve_password(self.path, configured_only=True)

    def test_plain_comic_stays_plain_despite_config_password(self):
        self.archive(password=None)
        document = ComicDocument(self.path)
        document.save({'Writer': 'Changed'})
        self.assertFalse(is_encrypted(self.path))
        self.assertEqual(ComicDocument(self.path).info.get_field('Writer'), 'Changed')

    def test_metadata_rewrite_retains_password_all_other_content_and_aes256(self):
        self.archive()
        before = archive_manifest(self.path, password=self.password)
        document = ComicDocument(self.path)
        document.save({'Writer': 'Changed'})
        after = archive_manifest(self.path, password=self.password)
        self.assertEqual({k: v for k, v in before.items() if k != 'ComicInfo.xml'},
                         {k: v for k, v in after.items() if k != 'ComicInfo.xml'})
        with pyzipper.AESZipFile(self.path) as archive:
            self.assertTrue(all(info.wz_aes_strength == 3 for info in archive.infolist()))
        self.assertEqual(ComicDocument(self.path).info.get_field('Writer'), 'Changed')
        with self.assertRaises(ArchivePasswordError):
            archive_manifest(self.path)

    def test_metadata_verification_failure_retains_original(self):
        self.archive()
        document = ComicDocument(self.path)
        before = self.path.read_bytes()
        with patch('features.comics.library.archive_manifest', return_value={}):
            with self.assertRaisesRegex(ValueError, 'verification'):
                document.save({'Writer': 'Changed'})
        self.assertEqual(self.path.read_bytes(), before)

    def test_mixed_encryption_is_readable_but_rejected_before_rewrite(self):
        self.archive()
        with pyzipper.AESZipFile(self.path, 'a') as archive:
            archive.writestr('plain.txt', b'plain')
        document = ComicDocument(self.path)
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Mixed encrypted/plain'):
            document.save({'Writer': 'Changed'})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(CBZFile(self.path).compress_to_webp())
        self.assertEqual(self.path.read_bytes(), before)

    def test_compression_plain_and_encrypted_have_identical_decrypted_results(self):
        for keep, preserve in [(False, True), (True, False)]:
            plain = self.root / ('plain-' + str(keep)) / 'comic.cbz'
            encrypted = self.root / ('encrypted-' + str(keep)) / 'comic.cbz'
            self.archive(plain, password=None)
            self.archive(encrypted)
            with patch('features.comics.compression_stats.datetime') as clock:
                clock.now.return_value = datetime(2020, 1, 2, 3, 4, 5)
                self.assertTrue(CBZFile(plain).compress_to_webp(keep, preserve))
                self.assertTrue(CBZFile(encrypted).compress_to_webp(keep, preserve))
            self.assertEqual(archive_manifest(plain), archive_manifest(encrypted, password=self.password))
            self.assertFalse(is_encrypted(plain))
            self.assertTrue(is_encrypted(encrypted))
            with open_archive(encrypted, password=self.password) as archive:
                self.assertTrue(all(info.wz_aes_strength == 3 for info in archive.infolist() if not info.is_dir()))

    def test_wrong_password_compression_keeps_original_and_counts_failure_without_prompt(self):
        self.archive()
        before = self.path.read_bytes()
        ComicDocument(self.path)  # Even a cached valid password cannot bypass a bad INI in compression.
        self.configure('incorrect-config')
        with patch('ui_new.dialogs.archive_password.ask_password', side_effect=AssertionError('No batch dialogs')):
            stats = compress_selected_cbz([self.path])
        self.assertEqual(stats.error_during_compression, 1)
        self.assertEqual(stats.compressed_file_count, 0)
        self.assertEqual(self.path.read_bytes(), before)

    def test_encrypted_line_edit_retains_password(self):
        self.archive(entries={'ComicInfo.xml': self.entries['ComicInfo.xml'], '1.png': self.entries['pages/1.png']})
        self.assertTrue(comic_info_xml_replace_author(self.path, 'Original'))
        self.assertEqual(ComicDocument(self.path).info.get_field('Writer'), self.path.parent.name)
        self.assertTrue(is_encrypted(self.path))

    def test_catalog_does_not_persist_decrypted_metadata(self):
        self.archive()
        result = LibraryCatalog(self.root).refresh()
        self.assertNotIn('Private series', str(result))
        self.assertEqual(result['count'], 0)
        cache = self.root / 'LogisticsComicsData/metadata.json'
        self.assertNotIn('Private series', cache.read_text())
        self.assertNotIn(self.password, cache.read_text())

    def test_configuration_error_does_not_echo_secret(self):
        self.config.write_text('[LogisticsZIP]\narchive_password = one\narchive_password = sensitive-secret\n')
        with self.assertRaises(ValueError) as caught:
            configured_password(self.path)
        self.assertNotIn('sensitive-secret', str(caught.exception))
        self.assertIn('DuplicateOptionError', str(caught.exception))

    def test_manual_unlock_survives_verified_metadata_replacement(self):
        self.archive()
        self.config.unlink()
        ComicDocument(self.path, password=self.password).save({'Writer': 'Edited'})
        self.assertEqual(ComicDocument(self.path).info.get_field('Writer'), 'Edited')

    def test_batch_reports_locked_comics_and_saves_accessible_ones_without_prompting(self):
        from features.comics.selection import ComicSelection
        self.archive()
        other = self.archive(self.path.parent / 'locked.cbz', password='different-test-password')
        selection = ComicSelection([self.path.parent])
        self.assertEqual(list(selection.load_failures), [other])
        before = other.read_bytes()
        result = selection.save({'Writer': 'Edited'})
        self.assertEqual(result.saved, [self.path])
        self.assertEqual(list(result.failed), [other])
        self.assertEqual(other.read_bytes(), before)

    def test_legacy_zipcrypto_metadata_rewrite_upgrades_to_aes256(self):
        import base64
        self.path.write_bytes(base64.b64decode('UEsDBBQACQAIABGFR13rua+rLgAAAC4AAAANAAAAQ29taWNJbmZvLnhtbMiAT0/VTDjeTeVjaP3opIXyOzsMRBN/OkNikTXXWSngDu4xAvKkgC+gjPT1NqFQSwcI67mvqy4AAAAuAAAAUEsDBAoACQAAABGFR10x3znpGgAAAA4AAAAIAAAAbm90ZS50eHTh22d/qwYLKkbvjHemYyF5XtNNZuenVTU521BLBwgx3znpGgAAAA4AAABQSwECHgMUAAkACAARhUdd67mvqy4AAAAuAAAADQAAAAAAAAABAAAApIEAAAAAQ29taWNJbmZvLnhtbFBLAQIeAwoACQAAABGFR10x3znpGgAAAA4AAAAIAAAAAAAAAAEAAACkgWkAAABub3RlLnR4dFBLBQYAAAAAAgACAHEAAAC5AAAAAAA='))
        self.configure("test-legacy")
        before = archive_manifest(self.path, password="test-legacy")
        ComicDocument(self.path).save({"Writer": "Updated"})
        after = archive_manifest(self.path, password="test-legacy")
        self.assertEqual(before["note.txt"], after["note.txt"])
        with open_archive(self.path, password="test-legacy") as archive:
            self.assertTrue(all(member.wz_aes_strength == 3 for member in archive.infolist()))

    def test_locked_background_previews_never_prompt(self):
        self.archive()
        self.config.unlink()
        with patch('ui_new.dialogs.archive_password.ask_password', side_effect=AssertionError('Unexpected prompt')):
            cbz = CBZFile(self.path)
            self.assertTrue(cbz.browser_thumbnail((120, 165)).startswith(b'\x89PNG'))
            details = cbz._comic_details()
            self.assertIn(('Archive', 'Locked'), details.fields)

    def test_default_password_does_not_bypass_missing_nearest_section_key(self):
        (self.path.parent / 'remoteConfig.ini').write_text('[DEFAULT]\narchive_password = unrelated\n[LogisticsZIP]\n')
        self.assertIsNone(configured_password(self.path))

    def test_multiple_entry_passwords_fail_before_metadata_or_compression_replacement(self):
        with pyzipper.AESZipFile(self.path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.setencryption(pyzipper.WZ_AES, nbits=256)
            archive.setpassword(self.password.encode('utf-8'))
            archive.writestr('ComicInfo.xml', self.entries['ComicInfo.xml'])
            archive.setpassword(b'other-test-password')
            archive.writestr('1.png', self.entries['pages/1.png'])
        before = self.path.read_bytes()
        with self.assertRaises(ArchivePasswordError):
            ComicDocument(self.path).save({'Writer': 'Edited'})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(CBZFile(self.path).compress_to_webp())
        self.assertEqual(self.path.read_bytes(), before)

    def test_zipcrypto_false_positive_header_password_still_requests_password(self):
        import base64
        self.path.write_bytes(base64.b64decode('UEsDBBQACQAIABGFR13rua+rLgAAAC4AAAANAAAAQ29taWNJbmZvLnhtbMiAT0/VTDjeTeVjaP3opIXyOzsMRBN/OkNikTXXWSngDu4xAvKkgC+gjPT1NqFQSwcI67mvqy4AAAAuAAAAUEsDBAoACQAAABGFR10x3znpGgAAAA4AAAAIAAAAbm90ZS50eHTh22d/qwYLKkbvjHemYyF5XtNNZuenVTU521BLBwgx3znpGgAAAA4AAABQSwECHgMUAAkACAARhUdd67mvqy4AAAAuAAAADQAAAAAAAAABAAAApIEAAAAAQ29taWNJbmZvLnhtbFBLAQIeAwoACQAAABGFR10x3znpGgAAAA4AAAAIAAAAAAAAAAEAAACkgWkAAABub3RlLnR4dFBLBQYAAAAAAgACAHEAAAC5AAAAAAA='))
        # This wrong password passes this fixture's one-byte ZipCrypto verifier.
        self.configure('wrong-test-31')
        with self.assertRaises(ArchivePasswordError):
            ComicDocument(self.path)
