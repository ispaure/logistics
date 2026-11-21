"""Platform PDF rendering adapter; document lifetime stays in the feature facade."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from contextlib import contextmanager, suppress
from pathlib import Path

from ..limits import PAGE_EDGE


@contextmanager
def _pdf_source(data):
    import os

    if isinstance(data, Path):
        with data.open('rb') as stream:
            yield stream
        return

    # Keep byte-backed private inputs in anonymous Linux memory.
    if hasattr(os, "memfd_create"):
        fd = os.memfd_create("logistics-pdf", 0)
    else:
        import ctypes
        import platform

        libc = ctypes.CDLL(None, use_errno=True)
        # memfd_create syscall numbers for Android's supported ABIs.
        number = {
            "aarch64": 279,
            "arm64": 279,
            "armv7l": 385,
            "x86_64": 319,
            "i686": 356,
        }.get(platform.machine())
        if number is None:
            raise ValueError("Anonymous PDF memory is unavailable on this device.")
        libc.syscall.restype = ctypes.c_long
        fd = libc.syscall(
            ctypes.c_long(number),
            ctypes.c_char_p(b"logistics-pdf"),
            ctypes.c_uint(0),
        )
        if fd < 0:
            raise OSError(
                ctypes.get_errno(), "Cannot allocate anonymous PDF memory"
            )
    with os.fdopen(fd, 'w+b') as stream:
        stream.write(data)
        stream.flush()
        stream.seek(0)
        yield stream


class AndroidPDF:
    def __init__(self, data):
        from java import jclass

        self.document = None
        descriptor = None
        try:
            with _pdf_source(data) as stream:
                descriptor = jclass("android.os.ParcelFileDescriptor").fromFd(
                    stream.fileno()
                )
                self.document = jclass("android.graphics.pdf.PdfRenderer")(descriptor)
                descriptor = None  # transferred to renderer
            self.count = self.document.getPageCount()
        except BaseException:
            # Retire whichever object owns the duplicate, preserving the
            # opening failure even if rollback also raises.
            resource = self.document if self.document is not None else descriptor
            if resource is not None:
                with suppress(BaseException):
                    resource.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.document.close()

    def page_size(self, index):
        page = self.document.openPage(index)
        try:
            return page.getWidth(), page.getHeight()
        finally:
            page.close()

    def render(self, index, *, edge=PAGE_EDGE):
        from java import jclass, jint

        page = self.document.openPage(index)
        bitmap = None
        try:
            scale = edge / max(page.getWidth(), page.getHeight(), 1)
            Bitmap = jclass("android.graphics.Bitmap")
            bitmap = Bitmap.createBitmap(
                max(1, round(page.getWidth() * scale)),
                max(1, round(page.getHeight() * scale)),
                Bitmap.Config.ARGB_8888,
            )
            # Chaquopy otherwise selects eraseColor(long), interpreting -1
            # as a packed ColorSpace value rather than an ARGB int.
            bitmap.eraseColor(jint(-1))
            page.render(bitmap, None, None, 1)
            output = jclass("java.io.ByteArrayOutputStream")()
            bitmap.compress(Bitmap.CompressFormat.PNG, 100, output)
            return bytes(output.toByteArray())
        finally:
            if bitmap is not None:
                bitmap.recycle()
            page.close()
