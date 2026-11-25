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
    @staticmethod
    def text_renderer():
        from java import jclass

        if jclass("android.os.Build$VERSION").SDK_INT >= 35:
            return "android.graphics.pdf.PdfRenderer"
        if (jclass("android.os.Build$VERSION").SDK_INT >= 30
                and jclass("android.os.ext.SdkExtensions").getExtensionVersion(31) >= 13):
            return "android.graphics.pdf.PdfRendererPreV"
        return None

    def __init__(self, data, *, text=False):
        from java import jclass

        self.document = None
        descriptor = None
        try:
            with _pdf_source(data) as stream:
                descriptor = jclass("android.os.ParcelFileDescriptor").fromFd(
                    stream.fileno()
                )
                renderer = self.text_renderer() if text else "android.graphics.pdf.PdfRenderer"
                if renderer is None:
                    raise ValueError("PDF text selection is unavailable on this Android version.")
                if renderer.endswith("PreV"):
                    params = jclass("android.graphics.pdf.LoadParams$Builder")().build()
                    self.document = jclass(renderer)(descriptor, params)
                else:
                    self.document = jclass(renderer)(descriptor)
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

    def select_text(self, index, start, end):
        from java import jclass

        page = self.document.openPage(index)
        try:
            w, h = page.getWidth(), page.getHeight()
            point = jclass("android.graphics.Point")
            boundary = jclass("android.graphics.pdf.models.selection.SelectionBoundary")
            selection = page.selectContent(boundary(point(round(start[0] * w), round(start[1] * h))),
                                           boundary(point(round(end[0] * w), round(end[1] * h))))
            if selection is None:
                return '', []
            text, rectangles = [], []
            contents = selection.getSelectedTextContents()
            for i in range(contents.size()):
                content = contents.get(i)
                text.append(str(content.getText()))
                bounds = content.getBounds()
                for j in range(bounds.size()):
                    rect = bounds.get(j)
                    rectangles.append((rect.left / w, rect.top / h, rect.width() / w, rect.height() / h))
            return '\n'.join(text), rectangles
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
