"""Platform PDF rendering adapter; document lifetime stays in the feature facade."""

from ..limits import PAGE_EDGE


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
            raise ValueError(
                "Cannot open PDF. It may be damaged or password protected."
            )
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
        image = self.document.render(
            index,
            QSize(
                max(1, round(size.width() * scale)),
                max(1, round(size.height() * scale)),
            ),
        )
        output = QBuffer()
        output.open(QIODevice.OpenModeFlag.WriteOnly)
        if image.isNull() or not image.save(output, "PNG"):
            raise ValueError("Cannot render this PDF page.")
        return bytes(output.data())
