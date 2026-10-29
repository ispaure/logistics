"""Reusable Logistics pdf fixtures; no test cases or discovery side effects."""
import base64
from contextlib import contextmanager


PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')

def search_fixture():
    from io import BytesIO
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    output = BytesIO()
    with PdfWriter() as writer:
        for text in ('needle first needle', 'middle page', 'last NEEDLE'):
            page = writer.add_blank_page(width=300, height=600)
            font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
            page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):
                DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
            content = DecodedStreamObject()
            content.set_data(f'BT /F1 18 Tf 20 500 Td (mobile-private-pdf-sentinel {text}) Tj ET'.encode())
            page[NameObject('/Contents')] = writer._add_object(content)
        writer.write(output)
    return output.getvalue()

PDF = search_fixture()

@contextmanager
def native_pdf(document):
    # Real PDF decoding is separately exercised with Qt;
    # this fixture keeps the mobile UI suite independent of desktop Qt imports.
    class Renderer:
        count = 3
        def render(self, index):
            return PNG
    yield Renderer()
