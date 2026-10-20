"""Platform PDF rendering adapter; document lifetime stays in the feature facade."""

from ..limits import PAGE_EDGE


class AndroidPDF:
    def __init__(self, data):
        # Anonymous Linux memory, never an app-cache plaintext file. PdfRenderer
        # owns the duplicated descriptor; the original is closed on every path.
        import os
        from java import jclass

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
        self.document = None
        descriptor = None
        try:
            with os.fdopen(fd, "w+b") as stream:
                stream.write(data)
                stream.flush()
                stream.seek(0)
                descriptor = jclass("android.os.ParcelFileDescriptor").fromFd(
                    stream.fileno()
                )
                self.document = jclass("android.graphics.pdf.PdfRenderer")(descriptor)
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
