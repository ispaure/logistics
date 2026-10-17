"""Bounded PNG/JPEG/WebP image validation before native decoding."""
import struct

MAX_IMAGE = 8 * 1024 * 1024


def webp_dimensions(data):
    """Read bounded static WebP canvas dimensions before native decoding."""
    if len(data) < 20 or data[:4] != b'RIFF' or data[8:12] != b'WEBP' or int.from_bytes(data[4:8], 'little') + 8 != len(data):
        raise ValueError('Invalid WebP page.')
    kind, size = data[12:16], int.from_bytes(data[16:20], 'little')
    if size > len(data) - 20 or size + (size & 1) > len(data) - 20:
        raise ValueError('Truncated WebP page.')
    chunk = data[20:20 + size]
    if kind == b'VP8X' and size == 10:
        if chunk[0] & 2:
            raise ValueError('Animated WebP images are not supported.')
        return 1 + int.from_bytes(chunk[4:7], 'little'), 1 + int.from_bytes(chunk[7:10], 'little')
    if kind == b'VP8L' and size >= 5 and chunk[0] == 0x2f:
        bits = int.from_bytes(chunk[1:5], 'little')
        if bits >> 29:
            raise ValueError('Unsupported WebP version.')
        return (bits & 0x3fff) + 1, ((bits >> 14) & 0x3fff) + 1
    if kind == b'VP8 ' and size >= 10 and not chunk[0] & 1 and chunk[3:6] == b'\x9d\x01\x2a':
        return int.from_bytes(chunk[6:8], 'little') & 0x3fff, int.from_bytes(chunk[8:10], 'little') & 0x3fff
    raise ValueError('Invalid WebP page header.')


def image_dimensions(data):
    if not isinstance(data, bytes) or len(data) > MAX_IMAGE:
        raise ValueError('Images are limited to 8 MiB.')
    if len(data) >= 33 and data[:8] == b'\x89PNG\r\n\x1a\n' and data[12:16] == b'IHDR':
        width, height = struct.unpack('>II', data[16:24])
    elif data.startswith(b'\xff\xd8'):
        offset, width, height = 2, 0, 0
        while offset + 4 <= len(data):
            if data[offset] != 255:
                raise ValueError('Invalid JPEG page.')
            while offset < len(data) and data[offset] == 255:
                offset += 1
            if offset >= len(data):
                break
            marker = data[offset]
            offset += 1
            if marker in (0xD9, 0xDA):
                break
            if marker == 0x01 or 0xD0 <= marker <= 0xD8:
                continue
            if offset + 2 > len(data):
                break
            length = int.from_bytes(data[offset:offset + 2], 'big')
            if length < 2 or offset + length > len(data):
                raise ValueError('Invalid JPEG segment.')
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                if length < 8:
                    raise ValueError('Invalid JPEG dimensions.')
                height, width = struct.unpack('>HH', data[offset + 3:offset + 7])
                break
            offset += length
    elif data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        width, height = webp_dimensions(data)
    else:
        raise ValueError('Use PNG, JPEG or WebP images.')
    if not 0 < width <= 8192 or not 0 < height <= 8192 or width * height > 16_000_000:
        raise ValueError('Page dimensions exceed the mobile 16-megapixel limit.')
    return width, height
