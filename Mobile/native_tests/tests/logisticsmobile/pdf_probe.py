"""Native PDF rasterization and reader controls using isolated synthetic files."""
import asyncio
import json
from pathlib import Path
import traceback
from logisticsmobile.app import LogisticsMobile


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
                    page = writer.add_blank_page(width=300, height=450)
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
            assert len(owner.pdf_search.results.matches) == 3, owner.pdf_search.status.text
            report['whole_document_search'] = True
            await asyncio.sleep(.3)
            await capture_window(self, output / 'search.png')
            owner.pdf_tools.close()
            owner.toggle_private_reading_mode()
            assert owner.reading_frame.immersive
            assert owner.reader_restore in owner.reading_frame.widget.children
            owner.toggle_private_reading_mode()
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
