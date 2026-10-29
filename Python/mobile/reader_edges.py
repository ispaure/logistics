"""Read platform edge geometry; shared reader policy owns the calculations."""
from commonUtils.ui.readers.layout import READER_LAYOUT, rounded_clearance, remaining_clearance


def progress_width(widget, available=None):
    """Measure the host allocation so an old caption cannot prevent shrinking."""
    container = getattr(widget._impl, 'container', None)
    width = available or getattr(container, 'width', 0) or widget.layout.content_width
    backend = type(widget._impl).__module__
    if container is not None:
        if backend.startswith('toga_iOS.'):
            native = container.native
            measured = float(native.bounds.size.width - container.left_inset - container.right_inset)
            if measured > 0:
                width = min(width, measured)
        elif backend.startswith('toga_android.'):
            parent = getattr(container, 'native_parent', None)
            if parent is not None and parent.getWidth() > 0:
                width = min(width, container.scale_out(parent.getWidth()))
    return max(1, int(width - widget.style.margin_left - widget.style.margin_right))


def style_progress_caption(label):
    """Match the native storage subtitle, retaining Pack's measured font size."""
    backend = type(label._impl).__module__
    size = READER_LAYOUT.caption_size
    if backend.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass
        label._impl.native.font = ObjCClass('UIFont').systemFontOfSize(size)
    elif backend.startswith('toga_android.'):
        label._impl.native.setTextSize(size)


def refresh_progress_edges(footer):
    widget = footer.widget
    base = READER_LAYOUT.progress_margin
    # UIKit safe areas already include display curvature. Never infer a radius
    # from a model name or a private screen property. Older Android releases
    # likewise retain the system cutout/bar insets without a guessed radius.
    if not type(widget._impl).__module__.startswith('toga_android.'):
        return
    from java import jclass, jarray, jint
    if jclass('android.os.Build$VERSION').SDK_INT < 31:
        return
    native = widget._impl.native
    insets = native.getRootWindowInsets()
    if insets is None or native.getWidth() <= 0 or native.getHeight() <= 0:
        return
    activity = widget.app._impl.native
    decor = activity.getWindow().getDecorView()
    density = native.getResources().getDisplayMetrics().density
    point, origin = jarray(jint)(2), jarray(jint)(2)
    native.getLocationOnScreen(point)
    decor.getLocationOnScreen(origin)
    x, y = (point[0] - origin[0]) / density, (point[1] - origin[1]) / density
    width, height = native.getWidth() / density, native.getHeight() / density
    corners = []
    for position, right, bottom in ((0, False, False), (1, True, False), (2, True, True), (3, False, True)):
        corner = insets.getRoundedCorner(position)
        if corner is None:
            continue
        center = corner.getCenter()
        corners.append((bottom if footer.vertical else right, right if footer.vertical else bottom,
                        center.x / density, center.y / density, corner.getRadius() / density))
    leading, trailing = rounded_clearance(x if footer.vertical else y,
        x + width if footer.vertical else y + height, corners, vertical=footer.vertical)
    style = widget.style
    before = style.margin_top if footer.vertical else style.margin_left
    after = style.margin_bottom if footer.vertical else style.margin_right
    start, stop = (y, y + height) if footer.vertical else (x, x + width)
    default = 0 if footer.vertical else base
    first = max(default, remaining_clearance(start - before, leading, trailing=False)) if leading is not None else default
    last = max(default, remaining_clearance(stop + after, trailing)) if trailing is not None else default
    # Pack uses integer logical units. Round outward to preserve the full hit box.
    from math import ceil
    changes = (dict(margin_top=ceil(first), margin_bottom=ceil(last)) if footer.vertical else
               dict(margin_left=ceil(first), margin_right=ceil(last)))
    for name, value in changes.items():
        if getattr(style, name) != value:
            setattr(style, name, value)
