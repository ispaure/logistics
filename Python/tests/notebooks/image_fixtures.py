"""Small synthetic PNG and encrypted PDF notebooks for persistence checks."""
import base64
from io import BytesIO
import struct
import zlib
from pypdf import PdfWriter
from features.notebooks.notebook import Notebook


def png_source():
    def chunk(kind, data):
        return struct.pack('>I',len(data)) + kind + data + struct.pack('>I',zlib.crc32(kind+data))
    pixels = (b'\0' + bytes([80,160,40,150])*16)*12
    data = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR',struct.pack('>IIBBBBB',16,12,8,6,0,0,0))
            + chunk(b'IDAT',zlib.compress(pixels)) + chunk(b'IEND',b''))
    return 'data:image/png;base64,' + base64.b64encode(data).decode()


def paste_action():
    return dict(op='paste-image', src=png_source(), corners=[[100,100],[300,100],[300,250],[100,250]])


def locked_book(password='secret', algorithm='AES-256'):
    from features.notebooks.pdf_crypto import enable_aes
    enable_aes()
    book = Notebook.new('Locked notebook')
    writer = PdfWriter()
    writer.add_blank_page(width=420, height=560)
    writer.encrypt(password, algorithm=algorithm)
    output = BytesIO(); writer.write(output)
    book.members[book.id + '.pdf'] = output.getvalue()
    book.content['fileType'] = 'pdf'
    book.pages[0].record['redir'] = dict(value=0)
    return book
