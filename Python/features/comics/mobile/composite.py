"""Bounded, RAM-only spread composition for one native zoom/pan surface."""
from math import ceil, sqrt

MAX_PIXELS = 16_000_000
MAX_SIDE = 8192


def spread_geometry(sizes, viewport=None, *, seam=None, single_right=False):
    """Equal-height, aspect-preserving pages, in visual order; bound allocation."""
    from features.comics.reading import SPREAD_GAP
    if not 1 <= len(sizes) <= 2 or any(w <= 0 or h <= 0 for w, h in sizes):
        raise ValueError('A spread requires one or two nonempty pages.')
    if seam is not None and viewport and all(w < h for w, h in sizes):
        width, height = viewport
        scale = min(1, MAX_SIDE / width, MAX_SIDE / height, sqrt(MAX_PIXELS / (width * height)))
        width, height = max(2, int(width * scale)), max(1, int(height * scale))
        center = min(width - 1, max(1, round(width * seam)))
        rects = []
        for index, (w, h) in enumerate(sizes):
            slot = center if index == 0 and not single_right else width - center
            fit = min(slot / w, height / h)
            w, h = max(1, int(w * fit)), max(1, int(h * fit))
            # Inner page edges meet exactly at the seam, even for unequal pages.
            rects.append((center - w if index == 0 and not single_right else center, (height - h) // 2, w, h))
        return (width, height), rects
    height = max(h for w, h in sizes)
    source_gap = SPREAD_GAP
    if viewport is not None and len(sizes) == 2:
        viewport_width, viewport_height = viewport
        if viewport_width is not None and viewport_width > SPREAD_GAP:
            fit_height = (viewport_width - SPREAD_GAP) / sum(w / h for w, h in sizes)
            if viewport_height is not None and viewport_height > 1:
                fit_height = min(fit_height, viewport_height)
            # Keep small pages at least fit resolution so rounding a bitmap
            # pixel cannot turn the desktop-sized gutter into a wide stripe.
            height = max(height, ceil(fit_height))
            source_gap = SPREAD_GAP * height / max(1, fit_height)
    widths = [height * w / h for w, h in sizes]
    total = sum(widths) + source_gap * (len(sizes) - 1)
    scale = min(1, MAX_SIDE / total, MAX_SIDE / height, sqrt(MAX_PIXELS / (total * height)))
    # Round down to keep the combined bitmap within its allocation budget.
    height = max(1, int(height * scale))
    gap = max(1, round(source_gap * scale)) if len(sizes) == 2 else 0
    widths = [max(1, int(height * w / h)) for w, h in sizes]
    while (sum(widths) + gap > MAX_SIDE or (sum(widths) + gap) * height > MAX_PIXELS):
        height -= 1
        if height < 1:
            raise ValueError('Spread dimensions exceed the mobile bitmap limit.')
        widths = [max(1, int(height * w / h)) for w, h in sizes]
    x, rects = 0, []
    for width in widths:
        rects.append((x, 0, width, height))
        x += width + gap
    return (x - gap, height), rects


def compose_spread(data, *, right_to_left=False, viewport=None, seam=None):
    """Decode validated pages and draw into an owned native bitmap, without files."""
    import toga
    from toga.platform import get_factory
    from .validation import image_dimensions
    # Validate the complete spread before any native decoding/allocation.
    sizes = [image_dimensions(page) for page in data]
    if right_to_left:
        data, sizes = list(reversed(data)), list(reversed(sizes))
    # Keep half-point window centers representable and avoid rasterizing a
    # portrait spread at only one bitmap pixel per logical point.
    if seam is not None and viewport:
        viewport = tuple(max(1, round(value * 2)) for value in viewport)
    size, rects = spread_geometry(sizes, viewport=viewport, seam=seam,
                                  single_right=len(data) == 1 and right_to_left)
    images = [toga.Image(src=page) for page in data]
    backend = get_factory().Image.__module__
    if backend.startswith('toga_android.'):
        from android.graphics import Bitmap, Canvas, Paint, RectF
        bitmap = Bitmap.createBitmap(*size, Bitmap.Config.ARGB_8888)
        drawing = Canvas(bitmap)
        paint = Paint(Paint.FILTER_BITMAP_FLAG)
        for image, (x, y, width, height) in zip(images, rects):
            drawing.drawBitmap(image._impl.native, None, RectF(x, y, x + width, y + height), paint)
        return toga.Image(src=bitmap)
    if backend.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass, Block, objc_id, CGSize, CGRect
        format = ObjCClass('UIGraphicsImageRendererFormat').defaultFormat()
        format.scale, format.opaque = 1, False  # Pixel bound must not grow with device DPI.
        renderer = ObjCClass('UIGraphicsImageRenderer').alloc().initWithSize(CGSize(*size), format=format)
        def draw(context):
            for image, (x, y, width, height) in zip(images, rects):
                image._impl.native.drawInRect(CGRect((x, y), (width, height)))
        return toga.Image(src=renderer.imageWithActions(Block(draw, None, objc_id)))
    if backend.startswith('toga_dummy.'):
        # Toga's testing backend already owns Pillow images. No mobile dependency.
        from PIL import Image
        bitmap = Image.new('RGBA', size)
        for image, (x, y, width, height) in zip(images, rects):
            bitmap.alpha_composite(image._impl.native.raw.convert('RGBA').resize((width, height)), (x, y))
        return toga.Image(src=get_factory().Image.RAW_TYPE(bitmap))
    raise RuntimeError('Composite comic rendering requires Android or iOS.')
