"""Bounded orientation metadata for accepted still-image documents.

Only the primary TIFF IFD is inspected. Malformed optional metadata does not
make otherwise decodable pixels unavailable; native decoders validate pixels.
"""


def _tiff_orientation(data):
    if data.startswith(b'Exif\0\0'):
        data = data[6:]
    if len(data) < 8 or data[:2] not in (b'II', b'MM'):
        return 1
    order = 'little' if data[:2] == b'II' else 'big'
    def number(offset, size):
        if offset < 0 or offset + size > len(data):
            raise ValueError('Truncated EXIF')
        return int.from_bytes(data[offset:offset + size], order)
    try:
        if number(2, 2) != 42:
            return 1
        offset = number(4, 4)
        count = number(offset, 2)
        for index in range(min(count, 4096)):
            entry = offset + 2 + index * 12
            if number(entry, 2) == 274 and number(entry + 2, 2) == 3 and number(entry + 4, 4) == 1:
                value = number(entry + 8, 2)
                return value if 1 <= value <= 8 else 1
    except ValueError:
        pass
    return 1


def image_orientation(data):
    if data.startswith(b'\xff\xd8'):
        offset = 2
        while offset + 4 <= len(data) and data[offset] == 255:
            while offset < len(data) and data[offset] == 255:
                offset += 1
            if offset >= len(data):
                break
            marker = data[offset]
            offset += 1
            if marker in (0xDA, 0xD9):
                break
            if marker == 1 or 0xD0 <= marker <= 0xD8:
                continue
            size = int.from_bytes(data[offset:offset + 2], 'big')
            if size < 2 or offset + size > len(data):
                break
            payload = data[offset + 2:offset + size]
            if marker == 0xE1 and payload.startswith(b'Exif\0\0'):
                return _tiff_orientation(payload)
            offset += size
    elif data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        offset = 12
        while offset + 8 <= len(data):
            kind = data[offset:offset + 4]
            size = int.from_bytes(data[offset + 4:offset + 8], 'little')
            if offset + 8 + size > len(data):
                break
            if kind == b'EXIF':
                return _tiff_orientation(data[offset + 8:offset + 8 + size])
            offset += 8 + size + (size & 1)
    elif data.startswith(b'\x89PNG\r\n\x1a\n'):
        offset = 8
        while offset + 12 <= len(data):
            size = int.from_bytes(data[offset:offset + 4], 'big')
            if offset + 12 + size > len(data):
                break
            if data[offset + 4:offset + 8] == b'eXIf':
                return _tiff_orientation(data[offset + 8:offset + 8 + size])
            offset += 12 + size
    return 1
