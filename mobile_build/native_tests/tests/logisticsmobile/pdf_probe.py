"""Native PDF rasterization and reader controls using isolated synthetic files."""
import asyncio
import json
from pathlib import Path
import traceback
from mobile.app import LogisticsMobile


class PDFProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'pdf-probe-storage'
        super().startup()

    def on_running(self):
        if not getattr(self, '_pdf_probe_started', False):
            self._pdf_probe_started = True
            self.loop.create_task(self.probe())

    async def probe(self):
        output = Path(self.paths.cache) / 'pdf-evidence'
        output.mkdir(exist_ok=True)
        report = dict(success=False, backend=type(self._impl).__module__)
        try:
            await asyncio.sleep(.7)
            from io import BytesIO
            from pypdf import PdfWriter
            from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
            data = BytesIO()
            with PdfWriter() as writer:
                for number in range(3):
                    page = writer.add_blank_page(width=600 if number == 2 else 300, height=450)
                    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                        NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
                    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):
                        DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
                    text = DecodedStreamObject()
                    text.set_data(f'BT /F1 20 Tf 25 390 Td (PDF reader - page {number+1}) Tj 0 -40 Td (Searchable document) Tj ET'.encode())
                    page[NameObject('/Contents')] = writer._add_object(text)
                writer.write(data)
            path = self.private_root / 'native.pdf'
            path.write_bytes(data.getvalue())
            assert await self.open_download(path=path), self.cloud_status.value
            owner = self.private_sessions.active
            assert owner.crypt_reader.pdf.count == 3
            assert owner.crypt_image.image is not None
            report['opened_and_rendered'] = True
            from tests.logisticsmobile.fixtures import capture_window
            await asyncio.sleep(.5)
            await capture_window(self, output / 'reading.png')
            owner.pdf_tools.toggle()
            owner.pdf_number.value = '3'
            await owner.pdf_number.on_confirm()
            assert owner.crypt_page.value == 'Page 3'
            report['numeric_jump'] = True
            owner.pdf_search.input.value = 'Searchable'
            await owner.pdf_search.next_match()
            assert len(owner.pdf_search.controller.results.matches) == 3, owner.pdf_search.status.text
            report['whole_document_search'] = True
            await asyncio.sleep(.3)
            await capture_window(self, output / 'search.png')
            owner.pdf_tools.close()
            canvas = owner.crypt_image
            impl = canvas._impl
            apple = hasattr(impl, 'picture')
            def tap():
                if apple:
                    impl.native.toggleControls_(None)
                else:
                    impl.native.performClick()
            async def swipe(direction):
                if apple:
                    gesture = next(g for g in impl.swipes if int(g.direction) == (4 if direction > 0 else 8))
                    impl.native.pageSwipe_(gesture)
                else:
                    touch(0)
                    touch(1, -120 * density if direction > 0 else 120 * density)
                await owner._comic_swipe_task
            if not apple:
                from java import jclass, jfloat
                MotionEvent = jclass('android.view.MotionEvent')
                SystemClock = jclass('android.os.SystemClock')
                density = impl.native.getResources().getDisplayMetrics().density
                def touch(action, dy=0):
                    now = SystemClock.uptimeMillis()
                    event = MotionEvent.obtain(now, now, action,
                        jfloat(impl.native.getWidth()/2), jfloat(impl.native.getHeight()*.34 + dy), 0)
                    try:
                        impl.native.onTouchEvent(event)
                    finally:
                        event.recycle()
            normal_size = (float(impl.native.bounds.size.width), float(impl.native.bounds.size.height)) if apple else (impl.native.getWidth(), impl.native.getHeight())
            report['normal_viewport'] = normal_size
            await swipe(1)
            assert owner.crypt_page.value == 'Page 2'
            await swipe(-1)
            assert owner.crypt_page.value == 'Page 1'
            tap()
            assert owner.reading_frame.immersive
            assert owner.crypt_image.magnifier_enabled
            assert owner.reader_restore not in owner.reading_frame.widget.children
            await swipe(1)
            assert owner.crypt_page.value == 'Page 2'
            assert owner.crypt_image.magnifier_enabled
            await asyncio.sleep(.3)
            def check_fit(label):
                if apple:
                    viewport = impl.native.bounds.size
                    rect = impl.picture.convertRect(impl.picture.bounds, toView=impl.native)
                    width, height = float(viewport.width), float(viewport.height)
                    x, y = float(rect.origin.x), float(rect.origin.y)
                    shown_width, shown_height = float(rect.size.width), float(rect.size.height)
                    offset = impl.native.contentOffset
                    x, y = x - float(offset.x), y - float(offset.y)
                else:
                    from java import jclass
                    native = impl.native
                    rect = jclass('android.graphics.RectF')(0., 0.,
                        float(native.getDrawable().getIntrinsicWidth()), float(native.getDrawable().getIntrinsicHeight()))
                    native.getImageMatrix().mapRect(rect)
                    width, height = float(native.getWidth()), float(native.getHeight())
                    x, y = float(rect.left), float(rect.top)
                    shown_width, shown_height = float(rect.width()), float(rect.height())
                source_width, source_height = canvas.image.width, canvas.image.height
                scale = min(width/source_width, height/source_height)
                expected_width, expected_height = source_width*scale, source_height*scale
                measured = dict(viewport=[width, height], displayed=[shown_width, shown_height],
                    source=[source_width, source_height], origin=[x, y])
                report[label] = measured
                assert width > 0 and height > 0, measured
                assert abs(shown_width-expected_width) < 3 and abs(shown_height-expected_height) < 3, measured
                assert abs(x-(width-shown_width)/2) < 3 and abs(y-(height-shown_height)/2) < 3, measured
                assert width >= normal_size[0] and height > normal_size[1], measured
                assert abs(shown_width/shown_height-source_width/source_height) < .005, measured
            check_fit('portrait_fullscreen_fit')
            await capture_window(self, output / 'fullscreen.png')
            await swipe(1)
            assert owner.crypt_page.value == 'Page 3'
            await asyncio.sleep(.3)
            check_fit('landscape_fullscreen_fit')
            await capture_window(self, output / 'fullscreen-landscape.png')
            await swipe(-1)
            assert owner.crypt_page.value == 'Page 2'
            await asyncio.sleep(.3)
            if apple:
                from types import SimpleNamespace
                from rubicon.objc import CGPoint
                def location(target):
                    return impl.picture.convertPoint(CGPoint(impl.picture.bounds.size.width / 2,
                        impl.picture.bounds.size.height / 3), toView=target)
                impl.show_magnifier(SimpleNamespace(locationInView=location))
                assert impl.lens is not None
            else:
                touch(0)
                await asyncio.sleep(.55)
            await capture_window(self, output / 'magnifier.png')
            if apple:
                impl.hide_magnifier()
                assert impl.lens is None
            else:
                touch(1)
            assert owner.reading_frame.immersive
            assert owner.crypt_page.value == 'Page 2'
            report['fullscreen_magnifier'] = True
            report['native_swipe_both_modes'] = True
            tap()
            assert not owner.crypt_image.magnifier_enabled
            assert not owner.reading_frame.immersive
            report['reading_mode'] = True
            reader = owner.crypt_reader
            owner.clear_private_reader()
            assert not reader.pdf.data
            report['memory_cleared'] = True
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(report, indent=2))
        print('PDF_PROBE=' + json.dumps(report), flush=True)


def main():
    return PDFProbe('PDF Probe', 'io.github.ispaure.logisticspdfprobe')
