"""Synthetic native reader geometry and long-title acceptance checks."""
import asyncio
import json
from pathlib import Path
import struct
import traceback
from zipfile import ZipFile
import zlib

from logisticsmobile.app import LogisticsMobile

BUNDLE = 'io.github.ispaure.logisticsreaderspaceqa'


def portrait_png():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    rows = []
    for y in range(600):
        color = (235, 220, 188) if y < 300 else (130, 175, 195)
        row = bytes(color) * 400
        rows.append(b'\0' + row)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 400, 600, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b''.join(rows))) + chunk(b'IEND', b''))


class ReaderSpaceProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'synthetic-workspace'
        super().startup()

    def on_running(self):
        self.loop.create_task(self.check())

    async def check(self):
        result = {'success': False}
        try:
            await self.show_files()
            await asyncio.sleep(.5)
            path = self.private_root / 'A Long Comic Title - A Journey Through the Northern Mountains #1.cbz'
            with ZipFile(path, 'w') as archive:
                archive.writestr('page1.png', portrait_png())
                archive.writestr('page2.png', portrait_png())
            self.preferences.values['comic_layout'] = 'single'
            from commonUtils.runtime.document_access import LocalDocuments
            record = self.reader_manager().catalog.library_store.import_book(LocalDocuments(), path)
            assert await self.open_book(record['id'])
            owner = self.readers.active
            owner.set_reading_mode(False)
            await asyncio.sleep(1.5)
            view, content, footer = owner.library_view, owner.book_content, owner.reader_footer
            result['canvas'] = [content.layout.width, content.layout.height]
            result['reader'] = [view.layout.width, view.layout.height]
            result['footer_height'] = footer.layout.content_height
            result['button_height'] = owner.previous_page.layout.height
            result['slider_height'] = owner.page_footer.slider.layout.height
            from .fixtures import capture_window
            await capture_window(self, Path(self.paths.cache) / 'reader-space.png')
            assert view.style.margin == (0, 0, 0, 0)
            assert owner.page_footer.badge.parent is footer
            assert content.layout.width >= view.layout.width - 2
            assert footer.layout.content_height <= 50, result
            assert owner.previous_page.style.height >= 44
            result['zero_outer_margin_and_single_footer_row'] = True
            ios = type(self._impl).__module__.startswith('toga_iOS.')
            if ios:
                label = self._reader_title_label
                size = label.intrinsicContentSize
                size = size() if callable(size) else size
                result['title'] = {'text': str(label.text), 'width': float(label.bounds.size.width),
                                   'required_width': float(size.width)}
                assert str(label.text) == path.name
                if view.layout.width >= 700:
                    assert float(label.bounds.size.width) > 320
                    assert float(label.bounds.size.width) >= float(size.width)
                    result['full_title_fits_wide_pane'] = True
            from .fixtures import capture_window
            await capture_window(self, Path(self.paths.cache) / 'reader-space.png')
            result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'reader-space-result.json').write_text(json.dumps(result, indent=2))
        print('READER_SPACE_RESULT=' + json.dumps(result), flush=True)


def main():
    return ReaderSpaceProbe('Reader Space QA', BUNDLE)
