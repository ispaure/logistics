"""Read platform edge geometry; shared reader policy owns the calculations."""
from commonUtils.ui.readers.layout import READER_LAYOUT, rounded_clearance, remaining_clearance


def page_footer(view):
    """Find reader progress controls regardless of their current layout axis."""
    footer = getattr(view, '_reader_page_footer', None)
    if footer is not None:
        return footer
    for child in getattr(view, 'children', ()):
        footer = page_footer(child)
        if footer is not None:
            return footer
    return None


def passive_caption_tail(view):
    """Measure the noninteractive space below the reader's touch row."""
    footer = page_footer(view)
    if footer is None or footer.vertical:
        return 0
    return max(0, footer.widget.layout.content_height - footer.row.layout.content_height)


def _caption_margins(footer, home):
    height = footer.spacer.layout.content_height
    original = max(-10, min(2, home - 4 - height)) if home > 4 else -10
    return original, 2


def footer_bottom_extension(view, home):
    footer = page_footer(view)
    if footer is None or footer.vertical:
        return 0
    tail, limit = passive_caption_tail(view), max(0, home - 4)
    offset = getattr(getattr(footer, 'slider', None), '_reader_track_offset', 0)
    if not offset:
        return min(tail, limit)
    # User-selected midpoint between the original low footer and the raised
    # version. Average both caption tails as well as their bottom extensions.
    original, raised = _caption_margins(footer, home)
    current = footer.badge.style.margin_top
    original_tail = max(0, tail + original - current)
    raised_tail = max(0, tail + raised - current)
    return (min(original_tail + offset, limit) + min(raised_tail, limit)) / 2


def footer_touch_extension(view, home):
    """The intentional lower hit padding of the selected midpoint footer."""
    return max(0, footer_bottom_extension(view, home) - passive_caption_tail(view))


def clear_notebook_rail(web):
    binding = getattr(web, '_notebook_rail_binding', None)
    if binding is not None:
        blur, _, _ = binding
        blur.removeFromSuperview()
        web._notebook_rail_binding = None


def notebook_canvas_edges(view, container, edge, home):
    """Extend live paper behind the side rail and blur only the rail area."""
    web = getattr(view, '_notebook_canvas', None)
    if web is None or web.parent is not view:
        return False
    left = float(container.left_inset) if edge == 1 else 0
    right = float(container.right_inset) if edge == 2 else 0
    if left or right:
        from ..ios_content_background import reduce_transparency
        if reduce_transparency():
            left = right = 0
    if left or right:
        layout_notebook_rail(web, container, left, right)
    else:
        clear_notebook_rail(web)
    changed = (web.style.margin_left, web.style.margin_right) != (-left, -right)
    if changed:
        web.style.margin_left, web.style.margin_right = -left, -right
    view._notebook_viewport_insets = (left, right, home)
    return changed


def layout_notebook_rail(web, container, left, right):
    from rubicon.objc import ObjCClass, ObjCInstance, CGRect, CGPoint
    from ..screen_privacy import native_value
    native = web._impl.native
    parent = native_value(native, 'superview')
    if parent is None:
        return
    binding = getattr(web, '_notebook_rail_binding', None)
    if binding is None:
        # WebKit owns its scroll-edge effect. A material sibling lets UIKit
        # blur the live canvas, including DOM scrolling and fresh ink.
        effect = ObjCClass('UIBlurEffect').effectWithStyle(6)  # System ultra-thin material.
        blur = ObjCClass('UIVisualEffectView').alloc().initWithEffect(effect)
        blur.userInteractionEnabled = False
        blur.accessibilityElementsHidden = True
        mask_view = ObjCClass('UIView').alloc().init()
        mask = ObjCClass('CAGradientLayer').layer()
        mask_view.layer.addSublayer(mask)
        binding = web._notebook_rail_binding = (blur, mask_view, mask)
    blur, mask_view, mask = binding
    if native_value(blur, 'superview') != parent:
        parent.insertSubview(blur, aboveSubview=native)
    area = container.native.convertRect(container.native.bounds, toView=parent)
    width = left or right
    x = area.origin.x if left else area.origin.x + area.size.width - width
    # Match the host edge above the canvas too. Starting at the WKWebView's
    # top would cut a horizontal line across the material beside the toolbar.
    blur.frame = CGRect((x, area.origin.y), (width, area.size.height))
    mask_view.frame = mask.frame = blur.bounds
    colors = ObjCClass('UIColor')
    mask.colors = [ObjCInstance(colors.blackColor.colorWithAlphaComponent(alpha).CGColor)
                   for alpha in (0, .12, .5, .88, 1)]
    mask.locations = [0, .2, .45, .7, 1]
    mask.startPoint, mask.endPoint = (CGPoint(1, .5), CGPoint(0, .5)) if left else (CGPoint(0, .5), CGPoint(1, .5))
    # UIKit copies the mask for its internal effect views. Give it the mask
    # after setting its geometry so first open and rotation use the same bounds.
    blur.maskView = mask_view


def compact_apple_reader(container, *, notebook=None):
    """The reader owns the title row; keep only the hardware inset above it."""
    if container.content is None:
        return False
    app = container.content.interface.app
    if app is None:
        return False
    from ..document_location import side_title_reader
    # Title mounting can precede route_changed, while app.body still points at
    # the previous page. Measure this container's content, never that stale route.
    root = container.content.interface
    reader = notebook or side_title_reader(root)
    if reader is not None:
        view = reader
    else:
        body = getattr(app, 'body', None)
        if body is None or not body.children:
            return False
        view = body.children[0]
        if (view._impl.container is not container
                or (getattr(view, '_notebook_canvas', None) is None and page_footer(view) is None)):
            return False
    from ..screen_privacy import native_value
    window = native_value(container.native, 'window')
    if window is None:
        return False
    changed = False
    from ..ios_toolbar import vertical_edge
    from ..ios_system_occlusions import content_column_top
    edge = vertical_edge(getattr(container, 'controller', None))
    if reader is not None and getattr(reader, '_reader_top_band_state', None) is not None:
        # The native header owns actual system-region clearance inside content.
        origin = container.native.convertRect(container.native.bounds, toView=window).origin
        top = max(0, -float(origin.y))
        if abs(container.top_inset - top) > .5:
            container.top_inset = top
            changed = True
    elif reader is not None and edge:
        # Notes has interactive rows across the full content width. UIKit can
        # extend that width beneath the floating rail during a layout pass.
        if getattr(reader, '_notes_title_controls', ()) and edge in (1, 2):
            from ..ios_reader_chrome import occlusion_geometry
            width = float(container.native.bounds.size.width)
            regions = occlusion_geometry(container.native)
            if edge == 1:
                inset = max(80, *(x + w for x, _, w, _ in regions if x < width / 4), 0)
                if container.left_inset < inset:
                    container.left_inset = inset
                    changed = True
            else:
                inset = max(80, *(width - x for x, _, _, _ in regions if x >= width * .75), 0)
                if container.right_inset < inset:
                    container.right_inset = inset
                    changed = True
        # Calculate top clearance after excluding the rail so its status
        # cluster does not push down the Files tabs and document together.
        top = content_column_top(container, window)
        if abs(container.top_inset - top) > .5:
            container.top_inset = top
            changed = True
    home = float(window.safeAreaInsets.bottom)
    extension = footer_bottom_extension(view, home)
    original_bottom = float(container.native.safeAreaInsets.bottom)
    notebook = getattr(view, '_notebook_canvas', None) is not None
    if notebook:
        extension = home
        changed = notebook_canvas_edges(view, container, edge, home) or changed
    bottom = max(0, original_bottom - extension) if 0 < original_bottom <= home else original_bottom
    if container.bottom_inset != bottom:
        container.bottom_inset = bottom
        changed = True
    from ..appearance import reserve_navigation
    reserve_navigation(app, view=view)
    extend_bottom = getattr(view, '_reader_bottom_extension', None)
    if extend_bottom is not None:
        extension = 0
        if edge in (1, 2):
            frame = container.native.convertRect(container.native.bounds, toView=window)
            bottom_gap = (float(window.bounds.size.height - frame.origin.y - frame.size.height)
                          + container.bottom_inset + view.style.margin_bottom)
            extension = max(0, round(bottom_gap))
        changed = extend_bottom(extension) or changed
    return changed


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
    if type(widget._impl).__module__.startswith('toga_iOS.'):
        if not footer.vertical:
            from ..screen_privacy import native_value
            window = native_value(widget._impl.native, 'window')
            home = float(window.safeAreaInsets.bottom) if window is not None else 0
            original, raised = _caption_margins(footer, home)
            margin = (original + raised) / 2
            if footer.badge.style.margin_top != margin:
                footer.badge.style.margin_top = margin
        return
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
