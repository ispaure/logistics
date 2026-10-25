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


async def capture_window(app, path):
    from pathlib import Path
    from .timings import measure
    return await measure(app, 'screenshot', _capture_window(app, path), filename=Path(path).name)


async def _capture_window(app, path):
    """Capture the actual native window, including reparented navigation content."""
    import asyncio
    import os
    from commonUtils.runtime.platform import get_os, OS
    if get_os() is OS.IOS:
        from rubicon.objc import Block, objc_id
        from toga_iOS.libs import UIGraphicsImageRenderer
        from toga_iOS.images import nsdata_to_bytes
        native = app.main_window._impl.native
        renderer = UIGraphicsImageRenderer.alloc().initWithSize(native.bounds.size)
        def render(context):
            native.drawViewHierarchyInRect(native.bounds, afterScreenUpdates=True)
        data = nsdata_to_bytes(renderer.PNGDataWithActions(Block(render, None, objc_id)))
    else:
        from java import jclass
        decor = app._impl.native.getWindow().getDecorView()
        for attempt in range(100):
            width, height = int(decor.getWidth()), int(decor.getHeight())
            if width > 0 and height > 0:
                break
            await asyncio.sleep(.1)
        else:
            raise RuntimeError('The Android window did not acquire drawable bounds.')
        Bitmap = jclass('android.graphics.Bitmap')
        bitmap = Bitmap.createBitmap(width, height, jclass('android.graphics.Bitmap$Config').ARGB_8888)
        output = jclass('java.io.ByteArrayOutputStream')()
        try:
            decor.draw(jclass('android.graphics.Canvas')(bitmap))
            if not bitmap.compress(jclass('android.graphics.Bitmap$CompressFormat').PNG, 100, output):
                raise OSError('The Android window screenshot could not be encoded.')
            data = bytes(int(value) & 255 for value in output.toByteArray())
        finally:
            output.close()
            bitmap.recycle()
    assert data.startswith(b'\x89PNG') and len(data) > 64, 'Native screenshot was empty'
    with path.open('wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return path


def ios_toolbar_items(controller, *, leading=False):
    """Read public native groups, including separately pinned completion items."""
    nav = controller.navigationItem
    groups = nav.leadingItemGroups if leading else nav.trailingItemGroups
    items = [item for group in groups for item in group.barButtonItems]
    if not leading and nav.pinnedTrailingGroup is not None:
        items.extend(nav.pinnedTrailingGroup.barButtonItems)
    return items
