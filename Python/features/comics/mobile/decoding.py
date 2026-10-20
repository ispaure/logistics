"""Sampled native raster decoding for transient, RAM-only comic composition."""
from math import ceil


def sample_size(source, target):
    """Largest power of two that keeps both decoded dimensions at draw resolution."""
    factor = 1
    while all(ceil(value / (factor * 2)) >= needed for value, needed in zip(source, target)):
        factor *= 2
    return factor


def decode_page(data, size, target, backend):
    import toga
    if backend.startswith('toga_android.'):
        from android.graphics import BitmapFactory
        options = BitmapFactory.Options()
        options.inSampleSize = sample_size(size, target)
        bitmap = BitmapFactory.decodeByteArray(data, 0, len(data), options)
        if bitmap is None:
            raise ValueError('Cannot decode comic page.')
        return toga.Image(src=bitmap)
    if backend.startswith('toga_iOS.'):
        return _apple_thumbnail(data, min(max(size), max(target)))
    return toga.Image(src=data)


def _apple_thumbnail(data, maximum):
    from ctypes import c_void_p, c_size_t
    from rubicon.objc import ObjCInstance, ns_from_py
    from rubicon.objc.runtime import load_library
    from toga_iOS.libs import NSData, UIImage
    import toga
    imageio = load_library('ImageIO')
    core = load_library('CoreFoundation')
    imageio.CGImageSourceCreateWithData.argtypes = [c_void_p, c_void_p]
    imageio.CGImageSourceCreateWithData.restype = c_void_p
    imageio.CGImageSourceCreateThumbnailAtIndex.argtypes = [c_void_p, c_size_t, c_void_p]
    imageio.CGImageSourceCreateThumbnailAtIndex.restype = c_void_p
    core.CFRelease.argtypes = [c_void_p]
    core.CFRelease.restype = None
    # Read the framework's actual CFString keys rather than assuming their value.
    # Rubicon's NSString proxies are unhashable; use their actual string values
    # as Python keys, then let ns_from_py build the native dictionary.
    options = ns_from_py({str(ObjCInstance(c_void_p.in_dll(imageio, key))): value for key, value in (
        ('kCGImageSourceCreateThumbnailFromImageAlways', True),
        ('kCGImageSourceThumbnailMaxPixelSize', int(maximum)),
        ('kCGImageSourceShouldCacheImmediately', True))})
    raw = NSData.dataWithBytes(data, length=len(data))
    source = imageio.CGImageSourceCreateWithData(raw.ptr, None)
    if not source:
        raise ValueError('Cannot read comic page.')
    thumbnail = None
    try:
        thumbnail = imageio.CGImageSourceCreateThumbnailAtIndex(source, 0, options.ptr)
        if not thumbnail:
            raise ValueError('Cannot decode comic page.')
        image = UIImage.imageWithCGImage(c_void_p(thumbnail))
        return toga.Image(src=image)
    finally:
        if thumbnail:
            core.CFRelease(thumbnail)
        core.CFRelease(source)
