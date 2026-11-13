"""Native PDF rasterization and reader controls using isolated synthetic files."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
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
            await owner.move_private_page(0)
            canvas = owner.crypt_image
            report['regular_boundary'] = await check_boundary(canvas.scroll)
            await capture_window(self, output / 'boundary.png')
            await owner.move_private_page(2)
            await wait_viewport(canvas.scroll, lambda state: state['page'] == 2 and any(p[0] == 2 for p in state['visible']))
            canvas.set_zoom(2)
            await wait_viewport(canvas.scroll, lambda state: abs(state['zoom'] - 2) < .01)
            report['zoom_and_last_page'] = True
            reader = owner.crypt_reader
            owner.clear_private_reader()
            assert not reader.pdf.data
            report['memory_cleared'] = True
            from mobile.obsidian import open_vault
            from commonUtils.runtime.resources.local import LocalFiles
            root = output / 'vault'
            (root / '.obsidian').mkdir(parents=True, exist_ok=True)
            (root / 'Mixed.pdf').write_bytes(data.getvalue())
            (root / 'Readme.md').write_text('# Readme')
            library = await open_vault(self, LocalFiles(root), '', 'documents')
            try:
                assert await library.open_note('Mixed.pdf')
                preview = library.embedded
                report['library_boundary'] = await check_boundary(preview.pdf)
                await capture_window(self, output / 'library-boundary.png')
                await preview.turn(1)
                await wait_viewport(preview.pdf, lambda state: state['page'] == 1)
                assert await library.open_note('Readme.md')
                assert preview.pdf.closed and not preview.pdf.pages
                report['library_replacement'] = True
            finally:
                library.dispose()
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(report, indent=2))
        print('PDF_PROBE=' + json.dumps(report), flush=True)


async def wait_viewport(surface, predicate):
    # Read DOM state without consuming the production link/tap bridge.
    async with asyncio.timeout(15):
        while True:
            if surface.pending is None:
                state = await surface.js("""JSON.stringify((() => {
                    const scroll = document.getElementById('scroll');
                    const pages = [...document.querySelectorAll('.sheet img')];
                    const visible = pages.map(img => [Number(img.parentNode.dataset.page),
                        img.getBoundingClientRect().top, img.getBoundingClientRect().bottom])
                        .filter(([,top,bottom]) => bottom > 0 && top < scroll.clientHeight);
                    return {top:scroll.scrollTop, height:scroll.clientHeight, visible, mounted:pages.length};
                })())""")
                if state is not None:
                    state.update(page=surface.index, zoom=(surface.location or {}).get('zoom', 1))
                    if predicate(state):
                        return state
            await asyncio.sleep(.05)


async def check_boundary(surface):
    await wait_viewport(surface, lambda state: any(p[0] == 0 for p in state['visible']))
    await wait_viewport(surface, lambda state: state['mounted'] >= 2)
    tops = []
    for offset in (25, 45, 30):
        await surface.js(f"""JSON.stringify((() => {{
            const next = document.querySelector('.sheet[data-page="1"]');
            if (!next) return false;
            const scroll = document.getElementById('scroll');
            scroll.scrollTop = next.offsetTop - {offset};
            return true;
        }})())""")
        await asyncio.sleep(.3)
        state = await wait_viewport(surface, lambda state: {0, 1} <= {p[0] for p in state['visible']})
        assert state['mounted'] <= 7, state
        tops.append(state['top'])
    assert tops[1] < tops[2] < tops[0], tops
    return dict(scroll_offsets=tops, visible=state['visible'], mounted=state['mounted'],
                input='native WebView scroll offset')


def main():
    return PDFProbe('PDF Probe', 'io.github.ispaure.logisticspdfprobe')
