"""Self-contained PNG screenshot records, bounded before native decoding."""
import base64
import struct
from uuid import uuid4

MAX_IMAGES = 4
MAX_IMAGE_BYTES = 2 * 1024 * 1024
IMAGE_TOKENS = 2048  # Approximate reserve; the server's vision tokenizer is authoritative.


def image_bytes(record):
    return base64.b64decode(record['data'], validate=True)


def image_url(record):
    return 'data:image/png;base64,' + record['data']


def validate_images(images):
    if not isinstance(images, list) or len(images) > MAX_IMAGES:
        raise ValueError('Attach at most four screenshots per message.')
    seen = set()
    for record in images:
        if not isinstance(record, dict):
            raise ValueError('Invalid screenshot record.')
        key = record.get('id')
        if (not isinstance(key, str) or len(key) != 32 or any(c not in '0123456789abcdef' for c in key)
                or key in seen or record.get('mime') != 'image/png'):
            raise ValueError('Invalid screenshot identity or format.')
        seen.add(key)
        value = record.get('data')
        if not isinstance(value, str) or len(value) > 4 * ((MAX_IMAGE_BYTES + 2) // 3):
            raise ValueError('Screenshot exceeds the 2 MiB limit.')
        try:
            content = image_bytes(record)
        except (ValueError, TypeError) as error:
            raise ValueError('Invalid screenshot encoding.') from error
        if (len(content) > MAX_IMAGE_BYTES or len(content) < 33
                or content[:8] != b'\x89PNG\r\n\x1a\n' or content[12:16] != b'IHDR'):
            raise ValueError('Invalid or oversized PNG screenshot.')
        width, height = struct.unpack('>II', content[16:24])
        if not 1 <= width <= 2048 or not 1 <= height <= 2048:
            raise ValueError('Screenshot dimensions exceed 2048 pixels.')
        if type(record.get('width')) is not int or type(record.get('height')) is not int or (width, height) != (record['width'], record['height']):
            raise ValueError('Invalid screenshot dimensions.')
    return images


def encode_screenshot(image):
    from commonUtils.ui import pyside as qt
    if image.isNull():
        raise ValueError('The clipboard does not contain a screenshot.')
    if image.width() * image.height() > 64 * 1024 * 1024:
        raise ValueError('Clipboard image is too large.')
    image = image.scaled(2048, 2048, qt.Qt.AspectRatioMode.KeepAspectRatio,
                         qt.Qt.TransformationMode.SmoothTransformation) if max(image.width(), image.height()) > 2048 else image
    data = qt.QByteArray()
    buffer = qt.QBuffer(data)
    buffer.open(qt.QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, 'PNG'):
        raise ValueError('The screenshot could not be encoded.')
    record = dict(id=uuid4().hex, mime='image/png', width=image.width(), height=image.height(),
                  data=base64.b64encode(bytes(data)).decode('ascii'))
    validate_images([record])
    return record


def read_clipboard_image_file(path):
    """Finder offers file URLs plus an icon preview; read the file, not that icon."""
    from pathlib import Path
    from commonUtils.ui import pyside as qt
    source = Path(path)
    if not source.is_file() or source.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('Paste an image file smaller than 16 MiB.')
    with source.open('rb') as stream:
        content = stream.read(16 * 1024 * 1024 + 1)
    if len(content) > 16 * 1024 * 1024:
        raise ValueError('Paste an image file smaller than 16 MiB.')
    data = qt.QByteArray(content)
    buffer = qt.QBuffer(data)
    buffer.open(qt.QIODevice.OpenModeFlag.ReadOnly)
    reader = qt.QImageReader(buffer)
    # Raster formats only; do not interpret SVG or other document references.
    if bytes(reader.format()).lower() not in (b'png', b'jpeg', b'webp', b'tiff', b'bmp', b'gif'):
        raise ValueError('The copied file is not a supported raster image. Copy a PNG/JPEG screenshot or image pixels.')
    size = reader.size()
    if not size.isValid() or size.width() * size.height() > 64 * 1024 * 1024:
        raise ValueError('The copied image dimensions are invalid or too large.')
    reader.setAutoTransform(True)
    image = reader.read()
    if image.isNull():
        raise ValueError('The copied image file could not be decoded. Copy the screenshot pixels or save it again.')
    return image
