"""Synthetic native reader geometry and long-title acceptance checks."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import struct
import traceback
from zipfile import ZipFile
import zlib

from mobile.app import LogisticsMobile

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
            from commonUtils.runtime.resources.documents import LocalDocuments
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
            result['outer_margins'] = [view.style.margin_top, view.style.margin_right,
                                       view.style.margin_bottom, view.style.margin_left]
            assert view._reading_frame_owner.margin == 0
            assert owner.page_footer.badge.parent is footer
            assert content.layout.width >= view.layout.width - 2
            assert owner.page_footer.row.layout.content_height == 48, result
            assert footer.layout.content_height <= 86, result
            assert owner.previous_page.style.height >= 44
            result['zero_outer_margin_and_single_footer_row'] = True
            ios = type(self._impl).__module__.startswith('toga_iOS.')
            if ios:
                nav = self._reader_toolbar_controller.navigationItem
                result['title'] = {'text': str(nav.title), 'storage_subtitle': nav.titleView is not None}
                assert str(nav.title) == path.name
                assert nav.titleView is not None
                window = self.main_window._impl.native
                native = footer._impl.native
                rect = native.convertRect(native.bounds, toView=window)
                gap = float(window.bounds.size.height - rect.origin.y - rect.size.height)
                result['bottom_gap'] = gap
                result['home_inset'] = float(window.safeAreaInsets.bottom)
                assert result['home_inset'] - 1 <= gap <= result['home_inset'] + 1, result
            else:
                subtitle = view._android_storage_subtitle
                assert subtitle.getParent() is not None
                assert str(subtitle.getChildAt(subtitle.getChildCount() - 1).getText()) == 'On-device'
                result['storage_subtitle'] = True
            assert view._document_location_row.parent is None
            # Native subtitles stay in the title bar when controls are restored.
            owner.set_reading_mode(True)
            owner.set_reading_mode(False)
            await asyncio.sleep(.5)
            assert view._document_location_row.parent is None
            from .fixtures import capture_window
            await capture_window(self, Path(self.paths.cache) / 'reader-space.png')
            result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'reader-space-result.json').write_text(json.dumps(result, indent=2))
        print('READER_SPACE_RESULT=' + json.dumps(result), flush=True)


def main():
    return ReaderSpaceProbe('Reader Space QA', BUNDLE)
