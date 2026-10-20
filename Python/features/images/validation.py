"""Mobile reader image acceptance over reusable bounded header probes."""
from commonUtils.formats.image_headers import image_header

MAX_IMAGE = 8 * 1024 * 1024


def webp_dimensions(data):
    header = image_header(data, max_bytes=MAX_IMAGE)
    if header.format != 'webp':
        raise ValueError('Invalid WebP page.')
    if header.animated:
        raise ValueError('Animated WebP images are not supported.')
    return header.width, header.height


def image_dimensions(data):
    if not isinstance(data, bytes) or len(data) > MAX_IMAGE:
        raise ValueError('Images are limited to 8 MiB.')
    header = image_header(data, max_bytes=MAX_IMAGE)
    if header.animated:
        raise ValueError('Animated WebP images are not supported.')
    width, height = header.width, header.height
    if not 0 < width <= 8192 or not 0 < height <= 8192 or width * height > 16_000_000:
        raise ValueError('Page dimensions exceed the mobile 16-megapixel limit.')
    return width, height
