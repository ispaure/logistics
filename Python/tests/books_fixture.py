"""Self-contained EPUB fixtures; no downloaded or user books are required."""
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED


def make_book(path, *, version='3.0', nav=True):
    package = f'''<?xml version="1.0" encoding="UTF-8"?>
    <package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/"
       xmlns:custom="urn:books-test" version="{version}" unique-identifier="book-id">
      <metadata><dc:identifier id="book-id">urn:test:book</dc:identifier>
        <dc:title id="title">Sample Book</dc:title><dc:creator id="author">One Author</dc:creator>
        <dc:language>en</dc:language><dc:subject>Fiction</dc:subject>
        <meta property="file-as" refines="#author">Author, One</meta>
        <meta property="custom:keep">Preserve me</meta><!-- custom comment --></metadata>
      <manifest><item id="one" href="Text/one.xhtml" media-type="application/xhtml+xml"/>
        <item id="two" href="Text/two.xhtml" media-type="application/xhtml+xml"/>
        <item id="nav" href="nav.xhtml" properties="{'nav' if nav else ''}" media-type="application/xhtml+xml"/>
        <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/></manifest>
      <spine toc="ncx"><itemref idref="one"/><itemref idref="two"/></spine>
    </package>'''
    with ZipFile(path, 'w', compression=ZIP_DEFLATED) as archive:
        archive.comment = b'keep archive comment'
        archive.writestr('mimetype', b'application/epub+zip', compress_type=ZIP_STORED)
        archive.writestr('META-INF/container.xml', '''<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
          <rootfiles><rootfile full-path="OPS/book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>''')
        archive.writestr('OPS/book.opf', package)
        archive.writestr('OPS/nav.xhtml', '''<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
          <body><nav epub:type="toc"><ol><li><a href="Text/one.xhtml">First chapter</a>
          <ol><li><a href="Text/one.xhtml#nested">Nested section</a></li></ol></li>
          <li><a href="Text/two.xhtml">Second chapter</a></li></ol></nav></body></html>''')
        archive.writestr('OPS/toc.ncx', '''<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap>
          <navPoint><navLabel><text>NCX first</text></navLabel><content src="Text/one.xhtml"/>
          <navPoint><navLabel><text>NCX nested</text></navLabel><content src="Text/one.xhtml#nested"/></navPoint></navPoint>
          <navPoint><navLabel><text>NCX second</text></navLabel><content src="Text/two.xhtml"/></navPoint></navMap></ncx>''')
        archive.writestr('OPS/Text/one.xhtml', '''<html xmlns="http://www.w3.org/1999/xhtml"><head><style>body{color:red}</style>
          <script>danger()</script></head><body style="color:red;font-size:2px"><h1>First chapter</h1><p>HELLO world.</p>
          <h2 id="nested">Nested section</h2><p>More text.</p><a href="two.xhtml">Next</a></body></html>''')
        archive.writestr('OPS/Text/two.xhtml', '''<html xmlns="http://www.w3.org/1999/xhtml"><body><h1>Second chapter</h1>
          <p>Another chapter.</p></body></html>''')
        archive.writestr('OPS/unknown.dat', b'untouched\x00bytes')
    return path
