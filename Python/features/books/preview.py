"""Bounded, aspect-preserving cover previews; browser workers call this lazily."""
from commonUtils.ui import pyside as qt
from .epub import BookError


def cover_thumbnail(book, size):
    try:
        path = book.cover_path()
        if not path:
            return b'', 'No cover image is included in this book.'
        buffer = qt.QBuffer()
        buffer.setData(qt.QByteArray(book.read(path)))
        buffer.open(qt.QIODevice.OpenModeFlag.ReadOnly)
        reader = qt.QImageReader(buffer)
        dimensions = reader.size()
        if not dimensions.isValid() or dimensions.width() * dimensions.height() > 40_000_000:
            return b'', 'The cover image is too large or unsupported.'
        reader.setAutoTransform(True)
        reader.setScaledSize(dimensions.scaled(qt.QSize(*size), qt.Qt.AspectRatioMode.KeepAspectRatio))
        image = reader.read()
        if image.isNull():
            return b'', 'The cover image could not be decoded.'
        image = image.scaled(qt.QSize(*size), qt.Qt.AspectRatioMode.KeepAspectRatio,
                             qt.Qt.TransformationMode.SmoothTransformation)
        output = qt.QBuffer()
        output.open(qt.QIODevice.OpenModeFlag.WriteOnly)
        image.save(output, 'PNG')
        return bytes(output.data()), ''
    except (OSError, BookError) as error:
        return b'', str(error)
