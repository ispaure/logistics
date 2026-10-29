"""Consistent Qt orientation, including plugins that ignore WebP EXIF."""
from commonUtils.ui import pyside as qt
from features.images.orientation import image_orientation


def read_oriented(reader, data):
    orientation = image_orientation(data)
    # Apply known metadata exactly once. Other native formats (e.g. HEIF)
    # retain their plugin's container-orientation support.
    reader.setAutoTransform(orientation == 1)
    image = reader.read()
    matrices = {2: (-1, 0, 0, 1), 3: (-1, 0, 0, -1), 4: (1, 0, 0, -1),
                5: (0, 1, 1, 0), 6: (0, 1, -1, 0), 7: (0, -1, -1, 0),
                8: (0, -1, 1, 0)}
    if not image.isNull() and orientation in matrices:
        image = image.transformed(qt.QTransform(*matrices[orientation], 0, 0))
    return image


def image_thumbnail(data, size):
    """Bounded, oriented preview bytes; shared caches retain only these pixels."""
    if not isinstance(size, qt.QSize):
        size = qt.QSize(*size)
    buffer = qt.QBuffer()
    buffer.setData(data)
    buffer.open(qt.QIODevice.OpenModeFlag.ReadOnly)
    reader = qt.QImageReader(buffer)
    dimensions = reader.size()
    if not dimensions.isValid() or dimensions.width() * dimensions.height() > 16 * 1024 * 1024:
        return b''
    target = qt.QSize(size.height(), size.width()) if image_orientation(data) >= 5 else size
    reader.setScaledSize(dimensions.scaled(target, qt.Qt.AspectRatioMode.KeepAspectRatio))
    image = read_oriented(reader, data)
    if image.isNull():
        return b''
    image = image.scaled(size, qt.Qt.AspectRatioMode.KeepAspectRatio, qt.Qt.TransformationMode.SmoothTransformation)
    output = qt.QBuffer()
    output.open(qt.QIODevice.OpenModeFlag.WriteOnly)
    image.save(output, 'PNG')
    return bytes(output.data())
