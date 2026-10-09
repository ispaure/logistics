"""Navigation, resource boundaries and transactional EPUB metadata preservation."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZIP_STORED
from xml.etree import ElementTree as ET
from books_fixture import make_book
from features.books.epub import EPUBBook, BookError, OPF, DC, resolve_href
from features.books.metadata import save_metadata, package_metadata
from features.books.content import chapter_html
from features.books.preferences import ReadingState


class EPUBTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.path = make_book(self.folder / 'book.epub')

    def test_epub3_nested_toc_and_spine(self):
        book = EPUBBook(self.path)
        self.assertEqual(book.title, 'Sample Book')
        self.assertEqual(book.spine, ['OPS/Text/one.xhtml', 'OPS/Text/two.xhtml'])
        self.assertEqual([(ch.label, ch.depth, ch.fragment) for ch in book.chapters],
                         [('First chapter', 0, ''), ('Nested section', 1, 'nested'), ('Second chapter', 0, '')])

    def test_epub2_ncx(self):
        make_book(self.path, version='2.0', nav=False)
        book = EPUBBook(self.path)
        self.assertEqual(book.chapters[0].label, 'NCX first')
        self.assertEqual(book.chapters[1].depth, 1)

    def test_resource_boundary(self):
        self.assertEqual(resolve_href('OPS/Text/one.xhtml', '../two%20words.xhtml#part'), ('OPS/two words.xhtml', 'part'))
        for path in ('https://example.com/a', 'file:///etc/passwd', '//host/a', '../../../escape', '%2fetc/passwd', 'a\\b'):
            with self.subTest(path=path), self.assertRaises(BookError):
                resolve_href('OPS/Text/one.xhtml', path)

    def test_readable_inert_html_and_anchors(self):
        html = chapter_html(EPUBBook(self.path), 'OPS/Text/one.xhtml', foreground='#eeeeee', spacing=150)
        self.assertIn('HELLO world', html)
        self.assertIn('name="nested"', html)
        self.assertNotIn('danger()', html)
        self.assertNotIn('color:red', html)
        self.assertNotIn('ns0:', html)

    def test_xhtml_named_entities_do_not_need_an_external_dtd(self):
        from types import SimpleNamespace
        book = SimpleNamespace(read=lambda path: b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p>A&nbsp;B &copy; &amp; C</p></body></html>')
        html = chapter_html(book, 'chapter', foreground='#111111', spacing=150)
        self.assertIn('A\u00a0B © &amp; C', html)

    def test_second_reader_cannot_overwrite_first_metadata_save(self):
        first, second = EPUBBook(self.path), EPUBBook(self.path)
        save_metadata(first, {'title': ['First saved title']})
        with self.assertRaisesRegex(BookError, 'changed on disk'):
            save_metadata(second, {'title': ['Stale reader title']})
        self.assertEqual(EPUBBook(self.path).title, 'First saved title')

    def test_saving_through_symlink_updates_target_and_preserves_link(self):
        alias = self.folder / 'alias.epub'
        alias.symlink_to(self.path)
        save_metadata(EPUBBook(alias), {'title': ['Via alias']})
        self.assertTrue(alias.is_symlink())
        self.assertEqual(EPUBBook(self.path).title, 'Via alias')

    def test_save_preserves_resources_unknown_metadata_and_backups(self):
        original = self.path.read_bytes()
        with ZipFile(self.path) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        book, backup = save_metadata(EPUBBook(self.path), {'title': ['New Title'], 'creator': ['New Author', 'Second Author'],
                                                         'subject': ['New tag'], 'description': ['A description']})
        self.assertEqual(backup.read_bytes(), original)
        self.assertEqual(book.title, 'New Title')
        self.assertEqual(book.values('creator'), ['New Author', 'Second Author'])
        self.assertIn(b'custom comment', book.package_bytes)
        self.assertIn(b'xmlns:custom="urn:books-test"', book.package_bytes)
        self.assertIn(b'Preserve me', book.package_bytes)
        self.assertEqual(book.values('identifier'), ['urn:test:book'])
        with ZipFile(self.path) as archive:
            self.assertEqual(archive.infolist()[0].filename, 'mimetype')
            self.assertEqual(archive.infolist()[0].compress_type, ZIP_STORED)
            self.assertEqual(archive.comment, b'keep archive comment')
            for name, data in entries.items():
                if name != book.package_path:
                    self.assertEqual(archive.read(name), data)
        self.assertFalse(any(node.get('property') == 'file-as' for node in book.metadata_node))
        _, other_backup = save_metadata(book, {'title': ['Another title']})
        self.assertNotEqual(backup, other_backup)
        self.assertEqual(backup.read_bytes(), original)

    def test_external_change_rejected(self):
        book = EPUBBook(self.path)
        with ZipFile(self.path, 'a') as archive:
            archive.writestr('added', 'changed elsewhere')
        changed = self.path.read_bytes()
        with self.assertRaisesRegex(BookError, 'changed on disk'):
            save_metadata(book, {'title': ['Overwrite']})
        self.assertEqual(self.path.read_bytes(), changed)

    def test_cancel_and_replace_failure_preserve_original(self):
        original = self.path.read_bytes()
        with self.assertRaises(BookError):
            save_metadata(EPUBBook(self.path), {'title': ['Cancelled']}, cancelled=lambda: True)
        with patch('features.books.metadata.os.replace', side_effect=OSError('Cannot replace')):
            with self.assertRaises(OSError):
                save_metadata(EPUBBook(self.path), {'title': ['Cancelled']})
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(list(self.folder.glob('.*.epub')))

    def test_cancellation_mid_save_and_backup_failure_keep_original(self):
        original = self.path.read_bytes()
        checks = [0]
        def cancel():
            checks[0] += 1
            return checks[0] >= 7
        with self.assertRaisesRegex(BookError, 'cancelled'):
            save_metadata(EPUBBook(self.path), {'title': ['Cancelled mid-save']}, cancelled=cancel)
        with patch('features.books.metadata.shutil.copymode', side_effect=[None, OSError('Backup permissions')]):
            with self.assertRaises(OSError):
                save_metadata(EPUBBook(self.path), {'title': ['Backup failed']})
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(list(self.folder.glob('book.epub.bak*')))
        self.assertFalse(list(self.folder.glob('.*.epub')))

    def test_required_fields_and_refinement_removal(self):
        book = EPUBBook(self.path)
        with self.assertRaises(BookError):
            package_metadata(book, {'title': []})
        metadata = ET.fromstring(package_metadata(book, {'creator': []})).find(f'{{{OPF}}}metadata')
        self.assertIsNone(metadata.find(f'{{{DC}}}creator'))
        self.assertFalse(any(node.get('refines') == '#author' for node in metadata))

    def test_resource_limit_and_drm(self):
        with patch('features.books.epub.MAX_RESOURCE', 10), self.assertRaises(BookError):
            EPUBBook(self.path)
        with ZipFile(self.path, 'a') as archive:
            archive.writestr('META-INF/encryption.xml', '''<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container"
              xmlns:e="http://www.w3.org/2001/04/xmlenc#"><e:EncryptedData><e:CipherData>
              <e:CipherReference URI="OPS/Text/one.xhtml"/></e:CipherData></e:EncryptedData></encryption>''')
        with self.assertRaisesRegex(BookError, 'DRM'):
            EPUBBook(self.path)

    def test_separate_reading_state_and_invalid_json(self):
        first = ReadingState(self.path, folder=self.folder / 'state')
        second = ReadingState(self.folder / 'other.epub', folder=self.folder / 'state')
        first.save({'position': .5})
        second.save({'position': .25})
        self.assertEqual(first.load()['position'], .5)
        self.assertEqual(second.load()['position'], .25)
        first.path.write_text('invalid')
        self.assertEqual(first.load(), {})
