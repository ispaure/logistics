"""Cross-host format behavior over synthetic, disposable books and comics."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from zipfile import ZipFile

from books_fixture import make_book
from commonUtils.runtime.document_access import LocalDocuments
from features.books.content import chapter_html as desktop_html
from features.books.mobile.content import chapter_html, chapter_text
from features.books.mobile.navigation import chapter_labels
from features.books.epub import BookError
from logisticsmobile.library import LibraryStore
from services.document_readers import PrivateReader
from test_mobile_readers import png_page


class ReadingParityTests(unittest.TestCase):
    def test_named_entities_render_on_desktop_mobile_and_text_fallback(self):
        source = (b'<!DOCTYPE html SYSTEM "https://example.invalid/xhtml.dtd">'
                  b'<html><body><p>One&nbsp;&mdash;&copy; &amp; two</p>'
                  b'<script>private-script-sentinel</script></body></html>')
        book = SimpleNamespace(spine=['chapter.xhtml'], read=lambda path: source)
        desktop = desktop_html(book, 'chapter.xhtml', foreground='#000000', spacing=150)
        mobile = chapter_html(book, 0)
        for rendered in (desktop, mobile, chapter_text(book, 0)):
            self.assertIn('One\u00a0\u2014\u00a9 &', rendered.replace('&amp;', '&'))
            self.assertNotIn('private-script-sentinel', rendered)
            self.assertNotIn('https://example.invalid', rendered)
        book.read = lambda path: b'<html><body>&notARealEntity;</body></html>'
        for render in (lambda: desktop_html(book, 'chapter.xhtml', foreground='#000', spacing=150),
                       lambda: chapter_html(book, 0)):
            with self.assertRaises(BookError):
                render()

    def test_provider_and_imported_epub_labels_use_the_same_contents_titles(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = make_book(root / 'fixture.epub')
            private = PrivateReader(source.name, source.read_bytes())
            store = LibraryStore(root / 'Library')
            record = store.import_book(LocalDocuments(), source)
            _, imported = store.open(record['id'])
            self.assertEqual(private.labels, chapter_labels(imported))
            self.assertEqual(private.labels, ['1. First chapter', '2. Second chapter'])
            self.assertEqual(private.page(0), ('text', chapter_text(imported, 0)))

    def test_provider_comic_pages_ignore_resource_forks_and_match_import_order(self):
        image = png_page()
        content = BytesIO()
        with ZipFile(content, 'w') as archive:
            for name in ('page10.png', '__MACOSX/page1.png', '._page0.png', 'page2.png'):
                archive.writestr(name, image)
        original = content.getvalue()
        private = PrivateReader('comic.cbz', original)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'comic.cbz'
            source.write_bytes(original)
            store = LibraryStore(root / 'Library')
            record = store.import_book(LocalDocuments(), source)
            _, imported = store.open(record['id'])
            self.assertEqual(private.pages, imported.pages)
            self.assertEqual(private.pages, ['page2.png', 'page10.png'])
            self.assertEqual(private.page(0), ('image', image))
            self.assertEqual(source.read_bytes(), original)

    def test_browser_cover_uses_the_same_page_filter_as_readers(self):
        import base64
        from contextlib import contextmanager
        from logisticsmobile.browser_preview import callbacks
        image = png_page()
        content = BytesIO()
        with ZipFile(content, 'w') as archive:
            archive.writestr('__MACOSX/page0.png', b'resource fork, not an image')
            archive.writestr('page1.png', image)
        class Provider:
            @contextmanager
            def open(self, path):
                yield BytesIO(content.getvalue())
        class Client:
            supports_streaming = True
            def request(self, action, **values):
                self.action, self.values = action, values
                return {'data': base64.b64encode(image).decode()}
        client = Client()
        thumbnail, _ = callbacks(Provider(), client)
        self.assertEqual(thumbnail({'path': 'comic.cbz'}, (64, 64), lambda: False), image)
        self.assertEqual(client.action, 'image_thumbnail')
        self.assertEqual(base64.b64decode(client.values['data']), image)

    def test_provider_comic_does_not_silently_skip_unsupported_pages(self):
        for names in (('page1.png', 'page2.gif'), ('__MACOSX/page1.png',)):
            with self.subTest(names=names), TemporaryDirectory() as directory:
                source = Path(directory) / 'comic.cbz'
                with ZipFile(source, 'w') as archive:
                    for name in names:
                        archive.writestr(name, png_page())
                with self.assertRaisesRegex(ValueError, 'PNG/JPEG/WebP'):
                    PrivateReader(source.name, source.read_bytes())
                store = LibraryStore(Path(directory) / 'Library')
                with self.assertRaisesRegex(ValueError, 'PNG/JPEG/WebP'):
                    store.import_book(LocalDocuments(), source)
                self.assertEqual(list(store.root.iterdir()), [])
