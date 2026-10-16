"""Isolated synthetic fullscreen geometry check; never reads user credentials."""
import asyncio, json, traceback
from pathlib import Path
from logisticsmobile.app import LogisticsMobile
from logisticsmobile.comic_layout_check import fixture_reader

class Probe(LogisticsMobile):

    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'synthetic-reader'
        super().startup()
        self.loop.create_task(self.probe())

    async def probe(self):
        out = Path(self.paths.cache) / 'fullscreen-check'
        out.mkdir(exist_ok=True)
        report = {'success': False, 'samples': []}
        try:
            await asyncio.sleep(1)
            self._hinge_status = 2
            owner = await fixture_reader(self, out, pages=4)
            await asyncio.sleep(1)
            await owner.move_book_page(0)
            window = self.main_window._impl.native
            for hidden in (True, False, True):
                owner.set_reading_mode(hidden)
                await asyncio.sleep(1)
                page = owner.book_content.children[0]
                canvas = getattr(page, 'canvas', page)._impl
                r = canvas.native.convertRect(canvas.native.bounds, toView=window)
                image = canvas.interface.image._impl.native
                sample = dict(immersive=hidden, x=float(r.origin.x), width=float(r.size.width), window_width=float(window.bounds.size.width), insets=[float(window.safeAreaInsets.left), float(window.safeAreaInsets.right)], status_hidden=bool(window.windowScene.statusBarManager.isStatusBarHidden()), image=[float(image.size.width), float(image.size.height)])
                report['samples'].append(sample)
                if hidden:
                    assert abs(sample['x']) < 1 and abs(sample['width'] - sample['window_width']) < 2, sample
                    assert sample['status_hidden'], sample
            from zipfile import ZipFile
            from commonUtils.runtime.document_access import LocalDocuments
            from logisticsmobile.reader_ui import ReaderUI
            epub = out / 'synthetic.epub'
            with ZipFile(epub, 'w') as z:
                z.writestr('mimetype', 'application/epub+zip')
                z.writestr('META-INF/container.xml', '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
                z.writestr('book.opf', '<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata><dc:title>Fullscreen fixture</dc:title></metadata><manifest><item id="one" href="one.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="one"/></spine></package>')
                z.writestr('one.xhtml', '<html><body><h1>Fullscreen reading</h1><p>Comfortable margins remain available.</p></body></html>')
            record = owner.library_store.import_book(LocalDocuments(), epub)
            await ReaderUI.open_book(owner, record['id'])
            for hidden in (True, False):
                owner.set_reading_mode(hidden)
                await asyncio.sleep(1)
                report.setdefault('ebook', []).append(dict(immersive=hidden, status_hidden=bool(window.windowScene.statusBarManager.isStatusBarHidden()), margin=owner.library_view.style.margin_top, restore_visible=owner.reader_restore in owner.library_view.children))
                assert report['ebook'][-1]['status_hidden'] == hidden
                assert owner.library_view.style.margin_top == 16
                assert (owner.reader_restore in owner.library_view.children) == hidden
            self.show_home()
            await asyncio.sleep(1)
            report['restored_status'] = not bool(window.windowScene.statusBarManager.isStatusBarHidden())
            assert report['restored_status']
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        (out / 'result.json').write_text(json.dumps(report, indent=2))

def main():
    return Probe('Reader check', 'io.github.ispaure.logisticsmobile.fullscreenprobe')
