"""Reader anchors/search/spreads and recoverable mobile metadata publication."""
from io import BytesIO
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from tests.books_fixture import make_book
from commonUtils.runtime.resources.documents import LocalDocuments
from features.books.locations import ChapterText, contents, link_destination, utf16_length
from features.books.mobile.content import chapter_html
from features.comics.mobile.navigation import ComicNavigation, adjacent_comic
from mobile.library import LibraryStore
from tests.test_mobile_readers import png_page


def portrait(width=100, height=200):
    data = bytearray(png_page())
    data[16:24] = struct.pack('>II', width, height)
    return bytes(data)


class ReaderExpansionTests(unittest.TestCase):
    def test_utf16_search_wrap_casefold_and_anchor(self):
        chapter = ChapterText('<html><head><title>hidden</title></head><body>'
            '<p>😀 Straße first</p><h2 id="nested">Second STRASSE</h2></body></html>')
        self.assertEqual(chapter.anchors['nested'], utf16_length('😀 Straße first'))
        first = chapter.find('STRASSE')
        self.assertEqual(first, (3, 9))
        second = chapter.find('strasse', first[1])
        self.assertGreater(second[0], first[1])
        self.assertEqual(chapter.find('STRASSE', second[1]), first)
        self.assertIsNone(chapter.find('missing'))
        self.assertIsNone(chapter.find(' '))
        self.assertEqual(ChapterText('<body>abc</body>').find('abc', 1), (0, 3))

    def test_contents_fragments_and_local_link_validation(self):
        with TemporaryDirectory() as directory:
            source = make_book(Path(directory) / 'book.epub')
            from features.books.epub import EPUBBook
            book = EPUBBook(source)
            self.assertTrue(any(entry.fragment == 'nested' and entry.depth == 1 for entry in contents(book)))
            self.assertEqual(link_destination(book, 0, 'two.xhtml'), (1, ''))
            self.assertEqual(link_destination(book, 0, '#nested'), (0, 'nested'))
            for href in ('https://example.invalid', 'javascript:bad()', '../../../escape', '../unknown.dat'):
                with self.assertRaises(ValueError):
                    link_destination(book, 0, href)
            rendered = chapter_html(book, 0, links=True)
            self.assertIn('id="nested"', rendered)
            self.assertIn('reader-link:two.xhtml', rendered)
            self.assertNotIn('danger()', rendered)

    def test_precise_locations_and_legacy_bookmarks_survive_reopen(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = make_book(root / 'book.epub')
            store = LibraryStore(root / 'Library')
            record = store.import_book(LocalDocuments(), source)
            record = store.progress(record, 1, bookmark=True)
            location = dict(path='OPS/Text/two.xhtml', offset=14)
            record = store.progress(record, 1, location=location, bookmark=True)
            reopened, _ = LibraryStore(store.root).open(record['id'])
            self.assertEqual(reopened['location'], location)
            self.assertEqual(reopened['bookmarks'], [1])
            self.assertEqual(reopened['epub_bookmarks'], [location])
            updated = store.progress(reopened, 1, location=location, bookmark=True)
            self.assertEqual(updated['epub_bookmarks'], [])
            with self.assertRaises(ValueError):
                store.progress(updated, 1, location=dict(path='chapter', offset=True))
            self.assertEqual(store.read_record(record['id'])[0], updated)

    def test_spreads_respect_doublepage_landscape_bounds_and_previous(self):
        data = [portrait(), portrait(), portrait(200, 100), portrait(), portrait()]
        nav = ComicNavigation(lambda i: (data[i], 'image/png'), len(data), double_pages={3})
        viewport = (1200, 800)
        indices, images = nav.load(0, viewport=viewport, mode='double')
        self.assertEqual(indices, (0, 1))
        self.assertEqual(len(images), 2)
        nav.visible = indices
        self.assertEqual(nav.next(0), 2)
        self.assertEqual(nav.previous(2, viewport=viewport, mode='double'), 0)
        self.assertEqual(nav.load(2, viewport=viewport, mode='double')[0], (2,))
        self.assertEqual(nav.load(3, viewport=viewport, mode='double')[0], (3,))
        self.assertEqual(nav.load(4, viewport=viewport, mode='double')[0], (4,))
        self.assertEqual(nav.previous(0, viewport=viewport), None)
        self.assertEqual(nav.load(0, viewport=(400, 800), mode='auto')[0], (0,))
        self.assertEqual(nav.load(0, viewport=viewport, mode='auto')[0], (0, 1))

    def test_failed_second_page_does_not_commit_spread(self):
        nav = ComicNavigation(lambda i: (portrait() if i == 0 else b'broken', 'image/png'), 2)
        nav.visible = (0,)
        with self.assertRaises(ValueError):
            nav.load(0, viewport=(1200, 800), mode='double')
        self.assertEqual(nav.visible, (0,))
        self.assertEqual(adjacent_comic([('10','comic10.cbz'), ('2','comic2.cbz')], '2', 1), '10')
        self.assertIsNone(adjacent_comic([('2', 'comic2.cbz')], '2', -1))

    def test_mobile_auto_follows_orientation_and_spread_navigation(self):
        for right_to_left in (False, True):
            nav = ComicNavigation(lambda i: (portrait(90, 100), 'image/png'), 5, right_to_left=right_to_left)
            self.assertEqual(nav.load(0, viewport=(1100, 1000))[0], (0, 1))
            self.assertEqual(nav.load(0, viewport=(1000, 1100))[0], (0,))
            self.assertEqual(nav.load(0, viewport=(1000, 1000))[0], (0,))
            nav.visible = nav.load(0, viewport=(1100, 1000))[0]
            self.assertEqual(nav.next(0), 2)
            self.assertEqual(nav.previous(2, viewport=(1100, 1000)), 0)
            self.assertEqual(nav.previous(2, viewport=(1000, 1100)), 1)
            self.assertEqual(nav.load(4, viewport=(1100, 1000))[0], (4,))
            self.assertEqual(nav.load(0, viewport=(1100, 1000), mode='single')[0], (0,))

    def test_import_metadata_preserves_resources_digest_and_original_source(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = make_book(root / 'book.epub')
            original = source.read_bytes()
            store = LibraryStore(root / 'Library')
            record = store.import_book(LocalDocuments(), source)
            _, reader = store.open(record['id'])
            updated, book = store.save_metadata(record, reader, {'title': ['Edited']})
            self.assertEqual(book.title, 'Edited')
            self.assertNotEqual(updated['digest'], record['digest'])
            self.assertEqual(source.read_bytes(), original)
            with ZipFile(BytesIO(original)) as old, ZipFile(book.path) as new:
                for name in old.namelist():
                    if name != book.package_path:
                        self.assertEqual(old.read(name), new.read(name))
            self.assertEqual(LibraryStore(store.root).open(record['id'])[1].title, 'Edited')
            with self.assertRaises(OSError):
                store.save_metadata(record, reader, {'title': ['Stale']})

    def test_published_archive_recovers_after_record_write_failure(self):
        import mobile.library_edits as edits
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = make_book(root / 'book.epub')
            store = LibraryStore(root / 'Library')
            record = store.import_book(LocalDocuments(), source)
            _, reader = store.open(record['id'])
            atomic = edits.atomic_write_json
            def fail_record(path, *args, **kwargs):
                if Path(path) == store.path(record['id'], '.json'):
                    raise OSError('Record publication interrupted')
                return atomic(path, *args, **kwargs)
            with patch.object(edits, 'atomic_write_json', side_effect=fail_record):
                with self.assertRaises(OSError):
                    store.save_metadata(record, reader, {'title': ['Recover me']})
            self.assertTrue(store.edit_journal(record['id']).exists())
            loaded, book = LibraryStore(store.root).open(record['id'])
            self.assertEqual(book.title, 'Recover me')
            self.assertEqual(loaded['revision'], record['revision'] + 1)
            self.assertFalse(store.edit_journal(record['id']).exists())

    def test_batch_preflight_preserves_every_file_on_invalid_field(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = LibraryStore(root / 'Library')
            records = []
            for i in range(2):
                source = root / f'comic{i}.cbz'
                with ZipFile(source, 'w') as archive:
                    archive.writestr('page.png', portrait())
                    archive.writestr('ComicInfo.xml', f'<ComicInfo><Title>{i}</Title></ComicInfo>')
                records.append(store.import_book(LocalDocuments(), source))
            with self.assertRaises(ValueError):
                store.edit_comics(records, {'Month': '99'})
            for record in records:
                self.assertEqual(store.read_record(record['id'])[0], record)
            completed, errors = store.edit_comics(records, {'Publisher': 'Shared'})
            self.assertEqual(len(completed), 2)
            self.assertEqual(errors, [])
            for record in completed:
                _, reader = store.open(record['id'])
                self.assertEqual(reader.document.info.get_field('Publisher'), 'Shared')

    def test_invalid_edit_journal_never_replaces_record(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = make_book(root / 'book.epub')
            store = LibraryStore(root / 'Library')
            record = store.import_book(LocalDocuments(), source)
            record_bytes = store.path(record['id'], '.json').read_bytes()
            journal = store.edit_journal(record['id'])
            journal.write_text(json.dumps({'before': record, 'after': {'id': 'bad'}}))
            with self.assertRaises((ValueError, KeyError)):
                store.read_record(record['id'])
            self.assertEqual(store.path(record['id'], '.json').read_bytes(), record_bytes)
            self.assertTrue(journal.exists())
