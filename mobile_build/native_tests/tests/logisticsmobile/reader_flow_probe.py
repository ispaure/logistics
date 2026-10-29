"""Native document chrome, vertical PDF spreads and whole-book EPUB progress."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback

from .compact_reading_probe import CompactReadingProbe, epub_bytes
from .fixtures import capture_window
from .web_checks import wait_for_text


def pdf_bytes():
    """Five distinct portrait pages, generated without a native-test dependency."""
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R 5 0 R 7 0 R 9 0 R 11 0 R] /Count 5 >>']
    for index in range(5):
        stream = (f'{.85 - index * .08} .9 .95 rg 0 0 300 600 re f\n'
                  f'.2 .3 .4 rg 30 {60 + index * 70} 240 40 re f\n').encode()
        objects.extend([
            f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 600] /Resources << >> /Contents {4 + index * 2} 0 R >>'.encode(),
            f'<< /Length {len(stream)} >>\nstream\n'.encode() + stream + b'endstream'])
    data, offsets = bytearray(b'%PDF-1.4\n'), [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n')
    start = len(data)
    data.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        data.extend(f'{offset:010} 00000 n \n'.encode())
    data.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF'.encode())
    return bytes(data)


class ReaderFlowProbe(CompactReadingProbe):
    def startup(self):
        import logging
        logging.getLogger().addHandler(logging.FileHandler(Path(self.paths.cache) / 'reader-flow-python.log'))
        super().startup()

    async def settled(self, owner):
        for _ in range(150):
            await asyncio.sleep(.1)
            if not owner.cloud_busy:
                await asyncio.sleep(.3)
                if not owner.cloud_busy:
                    return
        raise AssertionError('PDF did not settle')

    async def probe(self):
        output = Path(self.paths.cache) / 'reader-flow-evidence'
        output.mkdir(exist_ok=True)
        report = dict(success=False)
        try:
            await self.rotate(False)
            root = self.storage_root
            root.mkdir(parents=True, exist_ok=True)
            pdf = root / 'Flow.pdf'
            pdf.write_bytes(pdf_bytes())
            await self.show_files()
            adapter = self.native_host.adapter
            original_mode = int(adapter.controller.mode)
            if adapter.sidebar_used:
                adapter.controller.sidebar.setHidden(False)
                await asyncio.sleep(.5)
            original_sidebar_hidden = bool(adapter.controller.sidebar.isHidden())
            assert await self.open_download(path=pdf), self.cloud_status.value
            owner = self.private_sessions.active
            await self.settled(owner)
            assert adapter.tabs_hidden()
            if adapter.sidebar_used:
                assert int(adapter.controller.mode) == 1
                assert adapter.controller.sidebar.isHidden()
            slider = owner.page_footer.slider
            assert slider.layout.height > slider.layout.width * 2, (slider.layout.width, slider.layout.height)
            await capture_window(self, output / 'pdf-portrait.png')
            await self.rotate(True)
            await self.settled(owner)
            assert owner.crypt_reader.pdf_navigation.indices == (0, 1), (owner.crypt_reader.pdf_navigation.indices, owner.private_comic_viewport())
            await capture_window(self, output / 'pdf-landscape.png')
            owner.crypt_image.page(1)
            await owner._comic_swipe_task
            assert owner.crypt_reader.pdf_navigation.indices == (2, 3)
            await owner.next_private_page()
            assert owner.crypt_reader.pdf_navigation.indices == (4,)
            await owner.previous_private_page()
            assert owner.crypt_reader.pdf_navigation.indices == (2, 3)
            owner.toggle_private_reading_mode()
            assert owner.page_footer.widget not in owner.pdf_body.children
            owner.toggle_private_reading_mode()
            assert owner.page_footer.widget in owner.pdf_body.children
            assert adapter.tabs_hidden()
            from mobile.external_display import comic_canvas
            assert comic_canvas(self.body) is owner.crypt_image
            from rubicon.objc import ObjCClass
            display = self.scene_manager.external_comics
            picture = ObjCClass('UIImageView').alloc().init()
            window = ObjCClass('UIWindow').alloc().initWithFrame(self.main_window._impl.native.bounds)
            display.ios['reader-flow-qa'] = window, picture
            try:
                display.select(self)
                assert picture.image == owner.crypt_image._impl.picture.image
                navigation = adapter.navigation[self.native_host.destinations.index('files')]
                navigation.popViewControllerAnimated(True)
                for _ in range(100):
                    await asyncio.sleep(.1)
                    if not self._document_tabs_hidden:
                        break
                assert not adapter.tabs_hidden()
                assert picture.image is None
            finally:
                display.ios.pop('reader-flow-qa', None)
                display.refresh()
            assert int(adapter.controller.mode) == original_mode
            assert bool(adapter.controller.sidebar.isHidden()) == original_sidebar_hidden
            await capture_window(self, output / 'documents-restored.png')
            epub = root / 'Flow.epub'
            epub.write_bytes(epub_bytes())
            from types import SimpleNamespace
            from services.documents.readers import PrivateReader
            copies = SimpleNamespace(root=root, offline=True, encrypted=False,
                open=lambda *args, **kwargs: PrivateReader('Flow.epub', epub_bytes()))
            assert await self.open_crypt(copies=copies, key='Flow.epub'), self.cloud_status.value
            owner = self.private_sessions.active
            await wait_for_text(owner.provider_epub_view.webview, 'Compact reading')
            owner.page_footer.slider.value = .5
            await owner.page_footer.release(owner.page_footer.slider)
            await wait_for_text(owner.provider_epub_view.webview, 'Compact reading')
            await asyncio.sleep(.5)
            assert .4 < owner.page_footer.slider.value < .6, owner.page_footer.slider.value
            assert 'through book' in owner.page_footer.spacer.accessible_name
            await capture_window(self, output / 'epub-progress.png')
            from commonUtils.runtime.resources.documents import LocalDocuments
            record = self.reader_manager().catalog.library_store.import_book(LocalDocuments(), epub)
            await self.open_book(record['id'])
            imported = self.readers.active
            await wait_for_text(imported.epub_view, 'Compact reading')
            imported.page_footer.slider.value = .5
            await imported.page_footer.release(imported.page_footer.slider)
            await wait_for_text(imported.epub_view, 'Compact reading')
            await asyncio.sleep(.5)
            assert .4 < imported.page_footer.slider.value < .6, imported.page_footer.slider.value
            report.update(success=True, sidebar=adapter.sidebar_used,
                          book_progress=owner.page_footer.slider.value)
        except Exception:
            report['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(report, indent=2))
        print('READER_FLOW=' + json.dumps(report), flush=True)


def main():
    ReaderFlowProbe('Reader flow QA', 'io.github.ispaure.logisticsreaderflowqa').main_loop()
