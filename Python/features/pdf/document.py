"""Bounded, memory-only PDF input and platform page rasterization."""
from contextlib import contextmanager
import sys

MAX_PDF = 32 * 1024 * 1024
MAX_PAGES = 10000
PAGE_EDGE = 2048


def page_index(value, count):
    """Convert the displayed, one-based page number without silently wrapping."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError('Enter a whole page number.') from None
    if not 1 <= number <= count:
        raise ValueError(f'Enter a page number from 1 to {count}.')
    return number - 1


def read_pdf(stream):
    """Read in bounded ranges, including providers with a per-read ceiling."""
    data = bytearray()
    while len(data) <= MAX_PDF:
        part = stream.read(min(1024 * 1024, MAX_PDF + 1 - len(data)))
        if not part:
            break
        data.extend(part)
    if len(data) > MAX_PDF:
        raise ValueError('PDF reading is limited to 32 MiB.')
    return bytes(data)


class PDFDocument:
    def __init__(self, data):
        if not data or len(data) > MAX_PDF:
            raise ValueError('PDF reading is limited to 32 MiB.')
        self.data = data
        with self.open() as document:
            self.count = document.count
        if not 1 <= self.count <= MAX_PAGES:
            self.data = b''
            raise ValueError('PDF must contain between 1 and 10,000 pages.')

    @classmethod
    def from_source(cls, name, source):
        with source.open(name) as stream:
            return cls(read_pdf(stream))

    @contextmanager
    def open(self):
        if not self.data:
            raise ValueError('PDF is closed.')
        backend = ApplePDF if sys.platform == 'ios' else AndroidPDF if sys.platform == 'android' or hasattr(sys, 'getandroidapilevel') else QtPDF
        with backend(self.data) as document:
            yield document

    def page(self, index):
        if not 0 <= index < self.count:
            raise ValueError('Page does not exist.')
        with self.open() as document:
            return document.render(index)

    def close(self):
        self.data = b''


class QtPDF:
    def __init__(self, data):
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        from PySide6.QtPdf import QPdfDocument
        self.buffer = QBuffer()
        self.buffer.setData(QByteArray(data))
        self.buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self.document = QPdfDocument()
        self.document.load(self.buffer)
        if self.document.status() != QPdfDocument.Status.Ready:
            self.document.close()
            self.buffer.close()
            raise ValueError('Cannot open PDF. It may be damaged or password protected.')
        self.count = self.document.pageCount()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.document.close()
        self.buffer.close()

    def render(self, index):
        from PySide6.QtCore import QBuffer, QIODevice, QSize
        size = self.document.pagePointSize(index)
        scale = PAGE_EDGE / max(size.width(), size.height(), 1)
        image = self.document.render(index, QSize(max(1, round(size.width() * scale)), max(1, round(size.height() * scale))))
        output = QBuffer()
        output.open(QIODevice.OpenModeFlag.WriteOnly)
        if image.isNull() or not image.save(output, 'PNG'):
            raise ValueError('Cannot render this PDF page.')
        return bytes(output.data())


class ApplePDF:
    def __init__(self, data):
        import ctypes
        from rubicon.objc import ObjCClass
        self.framework = ctypes.CDLL('/System/Library/Frameworks/PDFKit.framework/PDFKit')
        self.document = ObjCClass('PDFDocument').alloc().initWithData(
            ObjCClass('NSData').dataWithBytes(data, length=len(data)))
        if self.document is None or self.document.isLocked:
            raise ValueError('Cannot open PDF. It may be damaged or password protected.')
        self.count = int(self.document.pageCount)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.document = None

    def render(self, index):
        import ctypes
        from rubicon.objc import CGSize
        from rubicon.objc.runtime import load_library
        from rubicon.objc import objc_id, ObjCInstance
        image = self.document.pageAtIndex(index).thumbnailOfSize(CGSize(PAGE_EDGE, PAGE_EDGE), forBox=1)
        ui = load_library('UIKit')
        ui.UIImagePNGRepresentation.restype = objc_id
        ui.UIImagePNGRepresentation.argtypes = [objc_id]
        data = ObjCInstance(ui.UIImagePNGRepresentation(image))
        return ctypes.string_at(data.bytes, data.length)


class AndroidPDF:
    def __init__(self, data):
        # Anonymous Linux memory, never an app-cache plaintext file. PdfRenderer
        # owns the duplicated descriptor; the original is closed on every path.
        import os
        from java import jclass
        if hasattr(os, 'memfd_create'):
            fd = os.memfd_create('logistics-pdf', 0)
        else:
            import ctypes
            import platform
            libc = ctypes.CDLL(None, use_errno=True)
            # memfd_create syscall numbers for Android's supported ABIs.
            number = {'aarch64': 279, 'arm64': 279, 'armv7l': 385,
                      'x86_64': 319, 'i686': 356}.get(platform.machine())
            if number is None:
                raise ValueError('Anonymous PDF memory is unavailable on this device.')
            libc.syscall.restype = ctypes.c_long
            fd = libc.syscall(ctypes.c_long(number), ctypes.c_char_p(b'logistics-pdf'), ctypes.c_uint(0))
            if fd < 0:
                raise OSError(ctypes.get_errno(), 'Cannot allocate anonymous PDF memory')
        self.document = None
        descriptor = None
        try:
            with os.fdopen(fd, 'w+b') as stream:
                stream.write(data)
                stream.flush()
                stream.seek(0)
                descriptor = jclass('android.os.ParcelFileDescriptor').fromFd(stream.fileno())
                self.document = jclass('android.graphics.pdf.PdfRenderer')(descriptor)
                descriptor = None  # transferred to renderer
            self.count = self.document.getPageCount()
        finally:
            if descriptor is not None:
                descriptor.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.document.close()

    def render(self, index):
        from java import jclass, jint
        page = self.document.openPage(index)
        bitmap = None
        try:
            scale = PAGE_EDGE / max(page.getWidth(), page.getHeight(), 1)
            Bitmap = jclass('android.graphics.Bitmap')
            bitmap = Bitmap.createBitmap(max(1, round(page.getWidth() * scale)),
                max(1, round(page.getHeight() * scale)), Bitmap.Config.ARGB_8888)
            # Chaquopy otherwise selects eraseColor(long), interpreting -1
            # as a packed ColorSpace value rather than an ARGB int.
            bitmap.eraseColor(jint(-1))
            page.render(bitmap, None, None, 1)
            output = jclass('java.io.ByteArrayOutputStream')()
            bitmap.compress(Bitmap.CompressFormat.PNG, 100, output)
            return bytes(output.toByteArray())
        finally:
            if bitmap is not None:
                bitmap.recycle()
            page.close()
