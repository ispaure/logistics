"""Tiny generated files for native app tests; no user documents or downloads."""
import struct
from zipfile import ZipFile
import zlib


def png_page():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00\xff')) + chunk(b'IEND', b''))


def make_books(root):
    epub, comic = root / 'Fixture.epub', root / 'Fixture.cbz'
    with ZipFile(epub, 'w') as archive:
        archive.writestr('mimetype', 'application/epub+zip')
        archive.writestr('META-INF/container.xml', '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="book.opf" '
                        'media-type="application/oebps-package+xml"/></rootfiles></container>')
        archive.writestr('book.opf', '<package xmlns="http://www.idpf.org/2007/opf" '
                        'xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata><dc:title>Native Fixture</dc:title>'
                        '</metadata><manifest><item id="one" href="one.xhtml" media-type="application/xhtml+xml"/>'
                        '<item id="two" href="two.xhtml" media-type="application/xhtml+xml"/></manifest>'
                        '<spine><itemref idref="one"/><itemref idref="two"/></spine></package>')
        archive.writestr('one.xhtml', '<html><body><h1>Native EPUB first</h1><script>bad()</script></body></html>')
        archive.writestr('two.xhtml', '<html><body><h1>Native EPUB second</h1></body></html>')
    with ZipFile(comic, 'w') as archive:
        archive.writestr('page10.png', png_page())
        archive.writestr('page2.png', png_page())
    return epub, comic


# Synthetic pyzipper WinZip AES-256 fixture; contains only a memory remote.
AES_CREDENTIALS = 'UEsDBBQAAQBjACcuTV3J2bwINgAAABgAAAALAAsAZml4dHVyZS50eHQBmQcAAQBBRQMIAJ7Y0pSWyQhai4Ta0J12uXz0ODn7tWsc5tNblcWra+jflD6LxE8HzcWxhN7eUoRY9Fl3gDAmjVBLAQIUAxQAAQBjACcuTV3J2bwINgAAABgAAAALAAsAAAAAAAAAAACAAQAAAABmaXh0dXJlLnR4dAGZBwABAEFFAwgAUEsFBgAAAAABAAEARAAAAGoAAAAAAA=='
