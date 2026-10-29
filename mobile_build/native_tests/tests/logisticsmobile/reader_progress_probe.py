"""Native footer appearance and page/chapter scrubbing on synthetic documents."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback
from zipfile import ZipFile

from mobile.app import LogisticsMobile

BUNDLE = 'io.github.ispaure.logisticsreaderprogressqa'


class ReaderProgressProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'synthetic-workspace'
        super().startup()

    def on_running(self):
        self.loop.create_task(self.check())

    async def check(self):
        result = {'success': False, 'samples': {}}
        try:
            await self.show_files()
            await asyncio.sleep(.6)
            from commonUtils.runtime.resources.documents import LocalDocuments
            from commonUtils.runtime.resources.local import LocalFiles
            from features.pdf.mobile.copies import PDFCopies
            from .reader_space_probe import portrait_png
            from .fixtures import capture_window, make_books
            comic = self.private_root / 'Northern journey.cbz'
            with ZipFile(comic, 'w') as archive:
                for index in range(4):
                    archive.writestr(f'page{index}.png', portrait_png())
            epub, _ = make_books(self.private_root)
            from pypdf import PdfWriter
            pdf = self.private_root / 'Northern journey.pdf'
            with PdfWriter() as writer:
                for _ in range(3):
                    writer.add_blank_page(width=400, height=600)
                writer.write(pdf)
            self.preferences.values['comic_layout'] = 'single'
            ios = type(self._impl).__module__.startswith('toga_iOS.')
            for kind, path in (('comic', comic), ('epub', epub), ('pdf', pdf)):
                if kind == 'pdf':
                    assert await self.open_crypt(copies=PDFCopies(LocalFiles(path.parent)), key=path.name)
                    owner = self.private_sessions.active
                    view = owner.crypt_view
                else:
                    record = self.reader_manager().catalog.library_store.import_book(LocalDocuments(), path)
                    assert await self.open_book(record['id'])
                    owner = self.readers.active
                    owner.set_reading_mode(False)
                    view = owner.library_view
                await asyncio.sleep(1)
                footer = owner.page_footer
                assert footer.slider.enabled
                assert footer.badge.parent is footer.widget
                if footer.vertical:
                    assert footer.slider.layout.content_height > 88
                else:
                    assert footer.row.layout.content_height == 48
                    assert footer.spacer.layout.content_height > 0
                assert footer.previous.style.width == footer.previous.style.height == 48
                if ios:
                    native = footer.slider._impl.native
                    assert float(native.thumbImageForState(0).size.width) == 16
                    assert float(native.minimumTrackImageForState(0).size.height) == 4
                else:
                    native = footer.slider._impl.native
                    density = native.getResources().getDisplayMetrics().density
                    assert abs(native.getThumb().getIntrinsicWidth() / density - 16) <= 1
                footer.slider.value = footer.count - 1
                if ios:
                    native.sendActionsForControlEvents(1 << 6)
                    await asyncio.sleep(1)
                else:
                    await footer.release(footer.slider)
                target = owner._provider_displayed_index if kind == 'pdf' else owner.book_record['position']
                assert target == footer.count - 1, (kind, target, footer.count)
                result['samples'][kind] = {'height': footer.widget.layout.content_height,
                    'badge': footer.spacer.text, 'scrubbed_to': target,
                    'count': footer.count, 'native_small_thumb_and_slim_track': True}
                await capture_window(self, Path(self.paths.cache) / f'reader-progress-{kind}.png')
                if ios:
                    from rubicon.objc import Block, objc_id, ObjCClass
                    from toga_iOS.libs import UIGraphicsImageRenderer, CGRect
                    from toga_iOS.images import nsdata_to_bytes
                    from mobile.appearance import apple_color
                    native_footer = footer.widget._impl.native
                    window = self.main_window._impl.native
                    rect = native_footer.convertRect(native_footer.bounds, toView=window)
                    renderer = UIGraphicsImageRenderer.alloc().initWithSize(native_footer.bounds.size)
                    def draw(context):
                        apple_color('window').setFill()
                        ObjCClass('UIBezierPath').bezierPathWithRect(native_footer.bounds).fill()
                        # Toga flattens leaf controls into the window container.
                        # Render that hierarchy into the footer-sized viewport.
                        window.drawViewHierarchyInRect(CGRect((-float(rect.origin.x), -float(rect.origin.y)),
                            (float(window.bounds.size.width), float(window.bounds.size.height))), afterScreenUpdates=True)
                    data = renderer.PNGDataWithActions(Block(draw, None, objc_id))
                    (Path(self.paths.cache) / f'reader-progress-{kind}-footer.png').write_bytes(nsdata_to_bytes(data))
                self.request_reader_close(owner.session.id)
                for _ in range(30):
                    if owner.session.id not in self.workspace.sessions:
                        break
                    await asyncio.sleep(.1)
                assert owner.session.id not in self.workspace.sessions
            result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'reader-progress-result.json').write_text(json.dumps(result, indent=2))
        print('READER_PROGRESS_RESULT=' + json.dumps(result), flush=True)


def main():
    return ReaderProgressProbe('Reader Progress QA', BUNDLE)
