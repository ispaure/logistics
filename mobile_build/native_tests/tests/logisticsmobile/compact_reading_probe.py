"""Isolated Markdown/EPUB height and rotation checks on Android and iOS."""
import asyncio
from io import BytesIO
import json
from pathlib import Path
import sys
import traceback
from types import SimpleNamespace
from uuid import uuid4
from zipfile import ZipFile

from commonUtils.runtime.resources.documents import LocalDocuments
from commonUtils.runtime.resources.local import LocalFiles
from features.text_editor.resources import LocalTextCopies
from mobile.app import LogisticsMobile

BUNDLE = 'io.github.ispaure.logisticscompactprobe'


def epub_bytes():
    data = BytesIO()
    with ZipFile(data, 'w') as archive:
        archive.writestr('mimetype', 'application/epub+zip')
        archive.writestr('META-INF/container.xml', '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        archive.writestr('book.opf', '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata><dc:title>Compact reading</dc:title><dc:language>en</dc:language><dc:identifier>compact</dc:identifier></metadata><manifest><item id="one" href="one.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="one"/></spine></package>')
        archive.writestr('one.xhtml', '<html><head></head><body><h1>Compact reading</h1>' + '<p>Readable passage with enough text for several pages. </p>' * 100 + '</body></html>')
    return data.getvalue()


class CompactReadingProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('compact-reading-' + uuid4().hex)
        super().startup()

    def on_running(self):
        if not getattr(self, '_compact_probe_started', False):
            self._compact_probe_started = True
            self.loop.create_task(self.probe())

    async def rotate(self, landscape):
        if sys.platform == 'ios':
            from rubicon.objc import ObjCClass
            preferences = ObjCClass('UIWindowSceneGeometryPreferencesIOS').alloc().initWithInterfaceOrientations(8 if landscape else 2)
            self.main_window._impl.native.windowScene.requestGeometryUpdateWithPreferences(preferences, errorHandler=None)
        else:
            self._impl.native.setRequestedOrientation(0 if landscape else 1)
        for _ in range(40):
            await asyncio.sleep(.1)
            if (self.main_window.size.width > self.main_window.size.height) == landscape:
                break
        await asyncio.sleep(1)

    def height(self, widget):
        native = widget._impl.native
        if sys.platform == 'ios':
            return float(native.bounds.size.height)
        density = native.getResources().getDisplayMetrics().density
        return native.getHeight() / density

    async def measure(self, name, web, report):
        from .fixtures import capture_window
        body = self.routes.body()
        for orientation, landscape in (('portrait', False), ('landscape', True), ('portrait-return', False)):
            await self.rotate(landscape)
            metrics = json.loads(await web.evaluate_javascript('JSON.stringify({width:innerWidth,height:innerHeight,scroll:document.documentElement.scrollWidth})'))
            metrics.update(page=name, orientation=orientation, body_height=self.height(body), web_height=self.height(web))
            metrics['chrome_height'] = metrics['body_height'] - metrics['web_height']
            metrics['navigation_clearance'] = body.children[0].style.margin_bottom
            if sys.platform == 'ios':
                buttons = body.children[0]._native_reader_buttons()
                for button in buttons:
                    window = button._impl.native.window
                    window = window() if callable(window) else window
                    assert window is not None, button.accessible_name
                metrics['native_toolbar_buttons'] = len(buttons)
            report['samples'].append(metrics)
            self.record(report)
            assert metrics['web_height'] > 80, metrics
            assert -1 <= metrics['chrome_height'] - metrics['navigation_clearance'] <= 64, metrics
            assert metrics['scroll'] <= metrics['width'] + 1 or 'epub' in name, metrics
            await capture_window(self, self.storage_root / (name + '-' + orientation + '.png'))

    def record(self, report):
        (Path(self.paths.cache) / 'compact-reading-result.json').write_text(json.dumps(report, indent=2))

    async def probe(self):
        report = dict(passed=False, platform=sys.platform, samples=[])
        try:
            text = '# Compact Markdown\n\n' + 'A readable paragraph with **formatting**.\n\n' * 50
            document = self.store.create('Compact.md', text.encode())
            self.open_document(document.id)
            self.show_documents()
            owner = self.editor_view
            assert owner.save_button.parent is None
            assert owner.preview_edit.control_icon == 'edit'
            await self.measure('markdown', owner.preview, report)
            root = self.storage_root / 'fixtures'
            root.mkdir()
            (root / 'Local.md').write_text(text)
            (root / 'Book.epub').write_bytes(epub_bytes())
            copies = LocalTextCopies(LocalFiles(root))
            assert await self.open_crypt(copies=copies, key='Local.md')
            owner = self.private_sessions.active
            assert owner.crypt_save.parent is None
            if sys.platform == 'ios':
                assert owner.crypt_preview_button.parent is None
                assert hasattr(owner.crypt_preview_button, '_native_reader_item')
            else:
                assert owner.crypt_preview_button.parent is owner.reader_toolbar
            await self.measure('provider-markdown', owner.crypt_preview, report)
            owner.toggle_private_preview()
            owner.crypt_text.value = text + '\nChanged'
            await asyncio.sleep(.2)
            assert owner.crypt_save.enabled
            if sys.platform == 'ios':
                window = owner.crypt_save._impl.native.window
                assert (window() if callable(window) else window) is not None
            owner.crypt_text.value = text
            assert not owner.crypt_save.enabled
            owner.toggle_private_preview()
            from services.documents.readers import PrivateReader
            book_copies = SimpleNamespace(root=root, offline=True, encrypted=False,
                open=lambda *args, **kwargs: PrivateReader('Book.epub', epub_bytes()))
            assert await self.open_crypt(copies=book_copies, key='Book.epub'), self.cloud_status.value
            owner = self.private_sessions.active
            await self.measure('provider-epub', owner.provider_epub_view.webview, report)
            record = self.reader_manager().catalog.library_store.import_book(LocalDocuments(), root / 'Book.epub')
            await self.open_book(record['id'])
            await self.measure('epub', self.readers.active.epub_view, report)
            report['passed'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        finally:
            await self.rotate(False)
        self.record(report)
        print('COMPACT_READING=' + json.dumps(report), flush=True)


def main():
    CompactReadingProbe('Compact reading', BUNDLE).main_loop()
